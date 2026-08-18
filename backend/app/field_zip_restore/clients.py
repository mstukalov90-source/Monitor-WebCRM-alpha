"""Database / photo I/O adapters for ZIP restore."""

from __future__ import annotations

import io
import json
import os
import subprocess
import tarfile
from pathlib import Path
from typing import Any

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import RealDictCursor


class ProdClient:
    """CLI adapter: docker exec psql locally, or SSH to prod."""

    def __init__(self, host: str, *, local: bool = False) -> None:
        self.host = host
        self.local = local

    def psql(self, sql: str) -> str:
        if self.local:
            cmd = [
                "docker",
                "exec",
                "-i",
                "monitor-db",
                "psql",
                "-U",
                "monitor",
                "-d",
                "monitor",
                "-v",
                "ON_ERROR_STOP=1",
                "-t",
                "-A",
            ]
            proc = subprocess.run(cmd, input=sql, text=True, capture_output=True)
        else:
            remote = (
                "docker exec -i monitor-db psql -U monitor -d monitor "
                "-v ON_ERROR_STOP=1 -t -A"
            )
            cmd = [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=30",
                f"root@{self.host}",
                remote,
            ]
            proc = subprocess.run(cmd, input=sql, text=True, capture_output=True)
        if proc.returncode != 0:
            raise RuntimeError(f"psql failed ({proc.returncode}):\n{proc.stderr or proc.stdout}")
        return proc.stdout

    def psql_json(self, sql: str) -> Any:
        text = self.psql(sql).strip()
        if not text:
            return None
        return json.loads(text)

    def copy_photos(self, files: list[tuple[str, bytes, int]], dest_dir: str) -> None:
        if not files:
            return
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for name, payload, mtime in files:
                info = tarfile.TarInfo(name=name)
                info.size = len(payload)
                info.mode = 0o644
                info.mtime = mtime
                tar.addfile(info, io.BytesIO(payload))
        buf.seek(0)
        if self.local:
            cmd = ["tar", "-C", dest_dir, "-xzf", "-"]
            proc = subprocess.run(cmd, input=buf.getvalue(), capture_output=True)
        else:
            remote = f"mkdir -p {dest_dir} && tar -C {dest_dir} -xzf -"
            cmd = [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=30",
                f"root@{self.host}",
                remote,
            ]
            proc = subprocess.run(cmd, input=buf.getvalue(), capture_output=True)
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", "replace") if proc.stderr else ""
            raise RuntimeError(f"photo copy failed ({proc.returncode}): {err}")

    def apply_sql(self, statements: list[str]) -> None:
        wrapped = "BEGIN;\n" + ";\n\n".join(statements) + ";\nCOMMIT;\n"
        self.psql(wrapped)


class PgClient:
    """WebCRM adapter: current process PostgreSQL pool + local photo dir."""

    def __init__(self, conn: PgConnection) -> None:
        self.conn = conn

    def psql(self, sql: str) -> str:
        with self.conn.cursor() as cur:
            cur.execute(sql)
            if cur.description is None:
                return ""
            rows = cur.fetchall()
        lines = []
        for row in rows:
            lines.append("\t".join("" if value is None else str(value) for value in row))
        return "\n".join(lines)

    def psql_json(self, sql: str) -> Any:
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql)
            row = cur.fetchone()
        if not row:
            return None
        value = next(iter(row.values())) if isinstance(row, dict) else row[0]
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, str):
            return json.loads(value)
        return value

    def copy_photos(self, files: list[tuple[str, bytes, int]], dest_dir: str) -> None:
        if not files:
            return
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        for name, payload, mtime in files:
            safe = Path(name).name
            if safe != name or not safe:
                raise ValueError(f"unsafe photo name {name!r}")
            path = dest / safe
            path.write_bytes(payload)
            try:
                os.utime(path, (mtime, mtime))
            except OSError:
                pass

    def apply_sql(self, statements: list[str]) -> None:
        try:
            with self.conn.cursor() as cur:
                for stmt in statements:
                    cur.execute(stmt)
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
