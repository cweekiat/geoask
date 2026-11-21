"""Generative photo enhancement: make a blurry photo look sharper. For viewing only.

Unlike SEN2SR (physically constrained satellite super-resolution), these models *invent*
plausible detail. GeoAsk labels every output "AI-generated" and never measures from it.

    realesrgan-x4   Real-ESRGAN x4plus (Wang et al. 2021), BSD-3-Clause, 64 MB, no text guidance.
                    The RRDBNet generator is ported here, so only torch is needed.
    sd-x4-upscaler  Stable Diffusion x4 Upscaler (Stability AI), CreativeML Open RAIL++-M,
                    about 2 GB, follows a text description. Needs the `enhance` extra (diffusers).

Weights are downloaded only when the user asks (Settings › Offline models).
"""

from __future__ import annotations

import base64
import io
import json
import os
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path

MODELS_DIR = Path(os.environ.get("GEOASK_MODELS", Path.home() / ".cache" / "geoask" / "models"))
Progress = Callable[[str], None]

ENHANCERS = {
    "realesrgan-x4": {
        "title": "Real-ESRGAN ×4", "licence": "BSD-3-Clause", "guidance": False, "size_mb": 64,
        "url": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
        "sha256": "4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1",
        "file": "realesrgan/RealESRGAN_x4plus.pth"},
    "sd-x4-upscaler": {
        "title": "Stable Diffusion ×4 Upscaler", "licence": "CreativeML Open RAIL++-M", "guidance": True,
        "size_mb": None, "repo": "stabilityai/stable-diffusion-x4-upscaler", "file": "sd-x4-upscaler/model_index.json"},
}
SD_PATTERNS = ["model_index.json", "*/config.json", "*/*.json", "*/*.txt", "*/*fp16.safetensors"]


def installed(eid: str) -> bool:
    return (MODELS_DIR / ENHANCERS[eid]["file"]).exists()


def status() -> list[dict]:
    return [{"id": k, **{kk: v[kk] for kk in ("title", "licence", "guidance", "size_mb")},
             "installed": installed(k)} for k, v in ENHANCERS.items()]


def sd_size_mb() -> float:
    """Exact download size of the fp16 SD upscaler files, from the Hugging Face API."""
    import fnmatch

    url = f"https://huggingface.co/api/models/{ENHANCERS['sd-x4-upscaler']['repo']}/tree/main?recursive=true"
    with urllib.request.urlopen(url, timeout=20) as r:
        files = json.load(r)
    total = sum((f.get("lfs") or {}).get("size", f.get("size", 0)) for f in files if f.get("type") == "file"
                and any(fnmatch.fnmatch(f["path"], p) for p in SD_PATTERNS))
    return round(total / 1e6)


def fetch(eid: str, progress: Progress = lambda _m: None) -> Path:
    spec = ENHANCERS[eid]
    dest = MODELS_DIR / spec["file"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    if eid == "realesrgan-x4":
        part = dest.with_suffix(".part")
        req = urllib.request.Request(spec["url"], headers={"User-Agent": "geoask"})
        with urllib.request.urlopen(req, timeout=60) as r, open(part, "wb") as out:
            total = int(r.headers.get("Content-Length") or 0)
            done, last = 0, 0.0
            while chunk := r.read(1 << 20):
                out.write(chunk)
                done += len(chunk)
                if time.time() - last > 0.5:
                    progress(f"Downloading {spec['title']}: {done / 1e6:.0f} of {total / 1e6:.0f} MB")
                    last = time.time()
        import hashlib

        h = hashlib.sha256()
        with open(part, "rb") as f:
            while chunk := f.read(1 << 20):
                h.update(chunk)
        if h.hexdigest() != spec["sha256"]:
            part.unlink()  # a corrupted or tampered partial download is never installed
            raise ValueError(f"{spec['title']}: the download's checksum didn't match, so it wasn't installed.")
        part.replace(dest)
        return dest
    from huggingface_hub import snapshot_download  # installed with the `enhance` extra

    progress(f"Downloading {spec['title']} (fp16 files only)")
    snapshot_download(spec["repo"], local_dir=str(dest.parent), allow_patterns=SD_PATTERNS)
    return dest


# ---- Real-ESRGAN generator (RRDBNet), inference only ------------------------------------------

def _rrdbnet():
    import torch
    from torch import nn
    from torch.nn import functional as F

    class RDB(nn.Module):
        def __init__(self, nf=64, gc=32):
            super().__init__()
            self.conv1 = nn.Conv2d(nf, gc, 3, 1, 1)
            self.conv2 = nn.Conv2d(nf + gc, gc, 3, 1, 1)
            self.conv3 = nn.Conv2d(nf + 2 * gc, gc, 3, 1, 1)
            self.conv4 = nn.Conv2d(nf + 3 * gc, gc, 3, 1, 1)
            self.conv5 = nn.Conv2d(nf + 4 * gc, nf, 3, 1, 1)
            self.lrelu = nn.LeakyReLU(0.2, inplace=True)

        def forward(self, x):
            x1 = self.lrelu(self.conv1(x))
            x2 = self.lrelu(self.conv2(torch.cat((x, x1), 1)))
            x3 = self.lrelu(self.conv3(torch.cat((x, x1, x2), 1)))
            x4 = self.lrelu(self.conv4(torch.cat((x, x1, x2, x3), 1)))
            return self.conv5(torch.cat((x, x1, x2, x3, x4), 1)) * 0.2 + x

    class RRDB(nn.Module):
        def __init__(self, nf=64, gc=32):
            super().__init__()
            self.rdb1, self.rdb2, self.rdb3 = RDB(nf, gc), RDB(nf, gc), RDB(nf, gc)

        def forward(self, x):
            return self.rdb3(self.rdb2(self.rdb1(x))) * 0.2 + x

    class RRDBNet(nn.Module):
        def __init__(self, nf=64, nb=23, gc=32):
            super().__init__()
            self.conv_first = nn.Conv2d(3, nf, 3, 1, 1)
            self.body = nn.Sequential(*[RRDB(nf, gc) for _ in range(nb)])
            self.conv_body = nn.Conv2d(nf, nf, 3, 1, 1)
            self.conv_up1 = nn.Conv2d(nf, nf, 3, 1, 1)
            self.conv_up2 = nn.Conv2d(nf, nf, 3, 1, 1)
            self.conv_hr = nn.Conv2d(nf, nf, 3, 1, 1)
            self.conv_last = nn.Conv2d(nf, 3, 3, 1, 1)
            self.lrelu = nn.LeakyReLU(0.2, inplace=True)

        def forward(self, x):
            feat = self.conv_first(x)
            feat = feat + self.conv_body(self.body(feat))
            feat = self.lrelu(self.conv_up1(F.interpolate(feat, scale_factor=2, mode="nearest")))
            feat = self.lrelu(self.conv_up2(F.interpolate(feat, scale_factor=2, mode="nearest")))
            return self.conv_last(self.lrelu(self.conv_hr(feat)))

    return RRDBNet


def _device():
    import torch

    return "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"


def _realesrgan(img, progress: Progress):
    import numpy as np
    import torch
    from PIL import Image

    net = _rrdbnet()()
    sd = torch.load(MODELS_DIR / ENHANCERS["realesrgan-x4"]["file"], map_location="cpu", weights_only=True)
    net.load_state_dict(sd.get("params_ema", sd.get("params", sd)))
    net.eval().to(_device())
    progress("Generating detail with Real-ESRGAN ×4")
    x = torch.from_numpy(np.asarray(img, np.float32) / 255).permute(2, 0, 1)[None].to(_device())
    with torch.no_grad():
        y = net(x).clamp(0, 1)[0].permute(1, 2, 0).cpu().numpy()
    return Image.fromarray((y * 255).round().astype("uint8"))


def _sd_upscale(img, guidance: str, progress: Progress):
    import torch
    from diffusers import StableDiffusionUpscalePipeline

    progress("Loading Stable Diffusion ×4 Upscaler")
    dev = _device()
    pipe = StableDiffusionUpscalePipeline.from_pretrained(
        str((MODELS_DIR / ENHANCERS["sd-x4-upscaler"]["file"]).parent), variant="fp16",
        torch_dtype=torch.float16 if dev != "cpu" else torch.float32).to(dev)
    progress("Generating detail guided by your description" if guidance else "Generating detail")
    return pipe(prompt=guidance or "a sharp, detailed photograph", image=img, num_inference_steps=25).images[0]


def enhance_photo(photo, guidance: str, out_root: Path, progress: Progress = lambda _m: None,
                  prefer: str | None = None) -> dict:
    """Enhance a Photo (geoask.geolocate.images.Photo). Returns a result dict for the app's card."""
    from PIL import Image

    avail = [k for k in ENHANCERS if installed(k)]
    if not avail:
        raise ValueError("No image enhancer is installed. Download one in Settings › Offline models.")
    eid = prefer if prefer in avail else ("sd-x4-upscaler" if guidance and "sd-x4-upscaler" in avail
                                          else avail[0])
    img = Image.open(io.BytesIO(base64.b64decode(photo.jpeg_b64))).convert("RGB")
    limit = 256 if eid == "sd-x4-upscaler" else 512  # keep runs to seconds on a laptop
    img.thumbnail((limit, limit))
    out = _sd_upscale(img, guidance, progress) if eid == "sd-x4-upscaler" else _realesrgan(img, progress)
    rid = f"enhance_{int(time.time())}_{photo.index}"
    d = Path(out_root) / rid
    d.mkdir(parents=True, exist_ok=True)
    img.resize(out.size, Image.BICUBIC).save(d / "before.png")
    out.save(d / "after.png")
    res = {"id": rid, "tool": "enhance", "model": ENHANCERS[eid]["title"], "licence": ENHANCERS[eid]["licence"],
           "scale": 4, "guidance": guidance if ENHANCERS[eid]["guidance"] else "", "photo": photo.index,
           "generated": True, "size": list(out.size),
           "images": {"before": "before.png", "after": "after.png"}}
    (d / "result.json").write_text(json.dumps(res))
    return res
