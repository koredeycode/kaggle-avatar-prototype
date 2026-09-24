#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    value = json.loads(args.manifest.read_text())
    failures: list[str] = []
    for item in value.get("files", []):
        path = Path(item["path"])
        if not path.exists():
            failures.append(f"missing: {path}")
            continue
        expected = item.get("sha256")
        if expected and digest(path) != expected:
            failures.append(f"checksum: {path}")
    result = {"ok": not failures, "failures": failures, "files": len(value.get("files", []))}
    print(json.dumps(result, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
