"""Download photos from VPS via SCP/SFTP into local cache."""

from __future__ import annotations

import getpass
import logging
import subprocess
from pathlib import Path

from app.config import Settings

logger = logging.getLogger(__name__)


class SftpPhotoError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)


def resolved_cache_dir(settings: Settings) -> Path:
    raw = settings.photo_local_cache_dir.strip() or "./data/photo_cache"
    path = Path(raw)
    if not path.is_absolute():
        backend_dir = Path(__file__).resolve().parent.parent.parent
        path = (backend_dir / path).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def sftp_configured(settings: Settings) -> bool:
    return bool(settings.photo_sftp_enabled)


def photo_available_locally(
    image_name: str,
    storage_dir: Path,
    cache_dir: Path | None,
) -> bool:
    from app.photos.ai_photo import photo_file_path

    if photo_file_path(image_name, storage_dir) is not None:
        return True
    if cache_dir is not None and photo_file_path(image_name, cache_dir) is not None:
        return True
    return False


def _download_via_scp(
    host: str,
    user: str,
    remote_path: str,
    target: Path,
    *,
    port: int,
    identity_file: str,
) -> None:
    remote = f"{user}@{host}:{remote_path}"
    command = [
        "scp",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ConnectTimeout=30",
        "-P",
        str(port),
    ]
    if identity_file:
        key_path = str(Path(identity_file).expanduser())
        command.extend(["-i", key_path])
    command.extend([remote, str(target)])
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        if target.exists():
            target.unlink(missing_ok=True)
        stderr = (result.stderr or result.stdout or "").strip()
        raise SftpPhotoError(stderr or f"scp failed with code {result.returncode}")


def _download_via_paramiko(
    host: str,
    user: str,
    password: str | None,
    remote_path: str,
    target: Path,
    *,
    port: int,
    identity_file: str,
) -> None:
    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    connect_kwargs: dict = {
        "hostname": host,
        "port": port,
        "username": user,
        "look_for_keys": not identity_file,
        "allow_agent": not identity_file,
        "timeout": 30,
        "banner_timeout": 30,
        "auth_timeout": 30,
    }
    if identity_file:
        connect_kwargs["key_filename"] = identity_file
    if password:
        connect_kwargs["password"] = password
    try:
        client.connect(**connect_kwargs)
        sftp = client.open_sftp()
        sftp.get(remote_path, str(target))
        sftp.close()
    except Exception:
        if target.exists():
            target.unlink(missing_ok=True)
        raise
    finally:
        client.close()


def _resolve_identity_file(settings: Settings) -> str:
    raw = settings.photo_sftp_key_path.strip()
    if not raw:
        return ""
    path = Path(raw).expanduser()
    if not path.is_absolute():
        backend_dir = Path(__file__).resolve().parent.parent.parent
        path = (backend_dir / path).resolve()
    return str(path)


def ensure_photo_cached(image_name: str, settings: Settings) -> Path:
    from app.photos.ai_photo import photo_file_path

    storage_dir = Path(settings.photo_storage_dir)
    cache_dir = resolved_cache_dir(settings)

    existing = photo_file_path(image_name, storage_dir)
    if existing is not None:
        return existing

    cached = photo_file_path(image_name, cache_dir)
    if cached is not None:
        return cached

    if not settings.photo_sftp_enabled:
        raise SftpPhotoError("Photo file not found on server")

    remote_path = f"{settings.photo_sftp_remote_dir.rstrip('/')}/{image_name}"
    host = settings.photo_sftp_host.strip() or settings.db_host
    user = settings.photo_sftp_user.strip()
    password = settings.photo_sftp_password.strip() or None
    identity_file = _resolve_identity_file(settings)
    target = cache_dir / image_name
    scp_user = user or getpass.getuser()

    errors: list[str] = []
    try:
        _download_via_scp(
            host,
            scp_user,
            remote_path,
            target,
            port=settings.photo_sftp_port,
            identity_file=identity_file,
        )
    except SftpPhotoError as exc:
        errors.append(f"scp: {exc}")
        try:
            _download_via_paramiko(
                host,
                scp_user,
                password,
                remote_path,
                target,
                port=settings.photo_sftp_port,
                identity_file=identity_file,
            )
        except Exception as paramiko_exc:
            errors.append(f"sftp: {paramiko_exc}")
            logger.warning("Photo download failed for %s: %s", image_name, "; ".join(errors))
            raise SftpPhotoError(
                "Не удалось скачать фото с VPS. Настройте SSH: "
                f"PHOTO_SFTP_USER и PHOTO_SFTP_KEY_PATH в backend/.env, "
                f"или выполните: PHOTO_SFTP_USER=login ./scripts/sync_photos.sh. "
                f"{' | '.join(errors)}"
            ) from paramiko_exc

    cached = photo_file_path(image_name, cache_dir)
    if cached is None:
        raise SftpPhotoError("Скачанный файл не прошёл проверку")
    return cached
