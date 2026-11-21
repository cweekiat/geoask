"""Fetch Clay v1.5 and keep only what inference needs.

The official checkpoint (5.2 GB) bundles the MAE decoder, a frozen SAM teacher and training state.
GeoAsk needs only the encoder (~300M parameters), so this script:

1. downloads ``made-with-clay/Clay`` → ``v1.5/clay-v1.5.ckpt`` (resumable),
2. extracts ``model.encoder.*`` → fp16 ``clay-v1.5-encoder.pt`` (~0.6 GB),
3. deletes the full checkpoint, unless ``--keep``.

    python scripts/fetch_clay.py            # into ~/.cache/geoask/models
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path

import torch

URL = "https://huggingface.co/made-with-clay/Clay/resolve/main/v1.5/clay-v1.5.ckpt"
DEFAULT_DIR = Path.home() / ".cache" / "geoask" / "models"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    ap.add_argument("--keep", action="store_true", help="keep the full 5.2 GB checkpoint")
    a = ap.parse_args()
    a.dir.mkdir(parents=True, exist_ok=True)
    ckpt = a.dir / "clay-v1.5.ckpt"
    out = a.dir / "clay-v1.5-encoder.pt"

    if not ckpt.exists() and not out.exists():
        part = ckpt.with_suffix(".ckpt.part")
        subprocess.run(["curl", "-L", "-C", "-", "--fail", "--retry", "5", "-o", str(part), URL],
                       check=True)
        part.replace(ckpt)

    if not out.exists():
        print("extracting encoder weights…")
        state = torch.load(ckpt, map_location="cpu", mmap=True, weights_only=True)["state_dict"]
        enc = {k[len("model.encoder."):]: v.to(torch.float16).clone()
               for k, v in state.items() if k.startswith("model.encoder.")}
        n = sum(v.numel() for v in enc.values())
        torch.save({"state_dict": enc, "source": URL, "params": n}, out)
        print(f"saved {len(enc)} tensors, {n / 1e6:.0f}M parameters → {out} "
              f"({out.stat().st_size / 1e6:.0f} MB)")

    if ckpt.exists() and not a.keep:
        ckpt.unlink()
        print(f"removed {ckpt.name}")
    h = hashlib.sha256(out.read_bytes()).hexdigest()[:16]
    print(f"encoder ready: {out} sha256:{h}…")


if __name__ == "__main__":
    main()
