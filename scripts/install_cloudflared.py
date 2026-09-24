#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import os
import platform
import shutil
import stat
import urllib.request
from pathlib import Path

DEFAULT_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"


def file_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=os.getenv("CLOUDFLARED_URL", DEFAULT_URL))
    parser.add_argument("--sha256", default=os.getenv("CLOUDFLARED_SHA256", ""))
    parser.add_argument("--path", type=Path, default=Path("/usr/local/bin/cloudflared"))
    args = parser.parse_args()
    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "amd64"}:
        raise SystemExit("This launcher expects Linux x86_64/amd64")
    if shutil.which("cloudflared") and str(shutil.which("cloudflared")) == str(args.path):
        print(f"cloudflared already exists: {args.path}")
        return 0
    args.path.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.path.with_suffix(".download")
    request = urllib.request.Request(args.url or DEFAULT_URL, headers={"User-Agent": "kaggle-avatar-prototype/0.1"})
    with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as stream:
        shutil.copyfileobj(response, stream)
    if args.sha256 and file_hash(temporary) != args.sha256:
        temporary.unlink(missing_ok=True)
        raise SystemExit("cloudflared checksum mismatch")
    temporary.replace(args.path)
    args.path.chmod(args.path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"installed {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
