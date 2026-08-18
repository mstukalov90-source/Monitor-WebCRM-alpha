#!/usr/bin/env python3
"""Refresh GET / cache-bust redirect in live WebCRM nginx configs."""
from __future__ import annotations

import re
import sys
from pathlib import Path

CANDIDATES = [
    Path("/etc/nginx/conf.d/monitor-webcrm.conf"),
    Path("/etc/nginx/sites-available/monitor-webcrm"),
]

EXACT_LOCATION_RE = re.compile(
    r"\n    location = /(?:index\.html)? \{.*?\n    \}\n",
    re.DOTALL,
)


def _guard(internal: bool) -> str:
    if not internal:
        return ""
    return """        if ($is_internal = 0) {
            return 403;
        }
"""


def location_slash_block(build: str, internal: bool) -> str:
    return f"""    location = / {{
{_guard(internal)}        add_header Cache-Control "no-store, no-cache, must-revalidate" always;
        add_header Pragma "no-cache" always;
        if ($arg_v != "{build}") {{
            return 302 /?v={build};
        }}
    }}
"""


def location_index_block(internal: bool) -> str:
    return f"""    location = /index.html {{
{_guard(internal)}        add_header Cache-Control "no-store, no-cache, must-revalidate" always;
        add_header Pragma "no-cache" always;
    }}
"""


def patch_text(text: str, build: str) -> str:
    internal = "$is_internal" in text
    stripped = EXACT_LOCATION_RE.sub("\n", text)
    block = "\n" + location_slash_block(build, internal) + "\n" + location_index_block(internal) + "\n"
    marker = "    location / {"
    idx = stripped.rfind(marker)
    if idx < 0:
        raise ValueError("SPA location / { not found")
    return stripped[:idx] + block + stripped[idx:]


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        print("usage: patch_nginx_cachebust.py BUILD_ID", file=sys.stderr)
        return 2
    build = sys.argv[1].strip()
    patched = 0
    for path in CANDIDATES:
        if not path.is_file():
            continue
        original = path.read_text()
        updated = patch_text(original, build)
        if updated == original:
            print(f"unchanged: {path}")
            continue
        backup = path.with_suffix(path.suffix + ".bak.cachebust")
        if not backup.exists():
            backup.write_text(original)
        path.write_text(updated)
        print(f"patched: {path} v={build}")
        patched += 1
    if patched == 0:
        print("no live nginx WebCRM config found", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
