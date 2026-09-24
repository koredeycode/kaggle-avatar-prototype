#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tarfile
import urllib.request
from pathlib import Path
from typing import Any

SHERPA_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-en-2023-06-26.tar.bz2"
SMART_TURN_URL = "https://huggingface.co/pipecat-ai/smart-turn-v3/resolve/main/smart-turn-v3.2-cpu.onnx"


def sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def download(url: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0:
        return destination
    temporary = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "kaggle-avatar-prototype/0.1"})
    with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as stream:
        shutil.copyfileobj(response, stream, length=1024 * 1024)
    temporary.replace(destination)
    return destination


def extract_tar(archive: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:bz2") as bundle:
        root = destination.resolve()
        for member in bundle.getmembers():
            target = (destination / member.name).resolve()
            if root not in target.parents and target != root:
                raise RuntimeError("archive contains an unsafe path")
        bundle.extractall(destination)
    return destination / archive.name.removesuffix(".tar.bz2")


def snapshot_kokoro(destination: Path) -> Path:
    from huggingface_hub import snapshot_download

    destination.mkdir(parents=True, exist_ok=True)
    return Path(
        snapshot_download(
            repo_id="hexgrad/Kokoro-82M",
            cache_dir=destination,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(os.getenv("MODEL_ROOT", "/kaggle/working/avatar-models")))
    parser.add_argument("--sherpa", action="store_true")
    parser.add_argument("--smart-turn", action="store_true")
    parser.add_argument("--kokoro", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {"root": str(args.root), "files": [], "errors": []}
    try:
        if args.sherpa:
            archive = download(SHERPA_URL, args.root / "sherpa-onnx-streaming-zipformer-en-2023-06-26.tar.bz2")
            model_dir = extract_tar(archive, args.root)
            manifest["sherpa_dir"] = str(model_dir)
            manifest["files"].append({"url": SHERPA_URL, "path": str(archive), "sha256": sha256(archive)})
        if args.smart_turn:
            smart_path = download(SMART_TURN_URL, args.root / "smart-turn-v3.2-cpu.onnx")
            manifest["smart_turn"] = str(smart_path)
            manifest["files"].append({"url": SMART_TURN_URL, "path": str(smart_path), "sha256": sha256(smart_path)})
        if args.kokoro:
            kokoro_dir = snapshot_kokoro(args.root / "huggingface" / "hub")
            manifest["kokoro_dir"] = str(kokoro_dir)
    except Exception as exc:
        manifest["errors"].append(str(exc))
        if args.strict:
            raise
    output = args.root / "model-manifest.json"
    output.write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))
    return 0 if not manifest["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
