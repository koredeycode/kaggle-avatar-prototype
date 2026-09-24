#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report: dict[str, object] = {
        "python": sys.version,
        "platform": platform.platform(),
        "cwd": str(Path.cwd()),
        "app_host": os.getenv("APP_HOST", "127.0.0.1"),
        "app_port": os.getenv("APP_PORT", "8000"),
        "model_mode": os.getenv("MODEL_MODE", "mock"),
        "gpu": None,
        "disk_bytes": shutil.disk_usage(Path.cwd()).free,
    }
    try:
        import torch

        report["torch"] = torch.__version__
        report["cuda"] = bool(torch.cuda.is_available())
        report["gpu_names"] = [torch.cuda.get_device_name(index) for index in range(torch.cuda.device_count())]
        report["gpu_memory_bytes"] = [
            int(torch.cuda.get_device_properties(index).total_memory)
            for index in range(torch.cuda.device_count())
        ]
    except Exception as exc:
        report["torch_error"] = str(exc)
    try:
        report["nvidia_smi"] = subprocess.check_output(["nvidia-smi"], text=True, timeout=5)
    except Exception as exc:
        report["nvidia_smi_error"] = str(exc)
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        for key, value in report.items():
            print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
