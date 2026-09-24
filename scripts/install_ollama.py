#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import urllib.request
from pathlib import Path

INSTALLER_URL = "https://ollama.com/install.sh"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=os.getenv("OLLAMA_INSTALLER_URL", INSTALLER_URL))
    args = parser.parse_args()
    if platform.system() != "Linux":
        raise SystemExit("This installer is intended for Linux/Kaggle")
    if shutil.which("ollama"):
        print("ollama already installed")
        return 0
    if not shutil.which("zstd"):
        raise SystemExit("zstd is required before installing Ollama; install it with apt-get")
    installer = Path("/tmp/ollama-install.sh")
    urllib.request.urlretrieve(args.url, installer)
    installer.chmod(0o700)
    subprocess.run(["bash", str(installer)], check=True)
    print(subprocess.check_output(["ollama", "--version"], text=True).strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
