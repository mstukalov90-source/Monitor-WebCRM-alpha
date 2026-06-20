#!/usr/bin/env bash
# Синхронизация фотографий с VPS в локальный кэш (один раз или по расписанию).
# Использование:
#   PHOTO_SFTP_USER=login ./scripts/sync_photos.sh
# Требуется SSH-доступ к VPS.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CACHE="${ROOT}/backend/data/photo_cache"
HOST="${PHOTO_SFTP_HOST:-77.222.63.161}"
USER="${PHOTO_SFTP_USER:-}"
REMOTE="${PHOTO_SFTP_REMOTE_DIR:-/opt/monitor/downloaded_photo}"

if [[ -z "$USER" ]]; then
  echo "Задайте PHOTO_SFTP_USER (SSH-логин на VPS), например:"
  echo "  PHOTO_SFTP_USER=login ./scripts/sync_photos.sh"
  exit 1
fi

mkdir -p "$CACHE"
echo "Синхронизация ${USER}@${HOST}:${REMOTE}/ -> ${CACHE}/"
rsync -avz --progress "${USER}@${HOST}:${REMOTE}/" "${CACHE}/"
echo "Готово. Перезапускать backend не нужно — кэш подхватится автоматически."
