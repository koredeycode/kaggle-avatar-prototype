#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid-file", default="/tmp/avatar-prototype-pids.json")
    args = parser.parse_args()
    path = Path(args.pid_file)
    if not path.exists():
        print(json.dumps({"status": "nothing_to_stop"}))
        return 0
    values = json.loads(path.read_text())
    stopped: list[int] = []
    for item in reversed(values.get("processes", [])):
        pid = int(item["pid"])
        try:
            os.killpg(pid, signal.SIGTERM)
            stopped.append(pid)
        except (ProcessLookupError, PermissionError):
            continue
    time.sleep(1)
    for pid in stopped:
        try:
            os.killpg(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    path.unlink(missing_ok=True)
    print(json.dumps({"status": "stopped", "pids": stopped}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
