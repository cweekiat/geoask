"""SEN2SR-Lite (RGBN ×4) network, ported for GeoAsk so no third-party code runs at load time.

Architecture: SPAN (Swift Parameter-free Attention Network, Wan et al. 2024) as packaged in the
``sen2sr`` project (ESA OpenSR / TACO foundation; model card licence CC0-1.0), followed by its
"hard constraint": an FFT blend that keeps the low frequencies of the real 10 m image and takes
only the high frequencies from the network. Downsampling the output therefore gives back the input
(up to resampling), which is what makes it a *display* aid rather than invented detail.

Only inference is ported: each Conv3XC block's three convolutions + skip are fused into one 3x3
convolution once, at load time (the same fusion the original does on every forward pass).
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch import nn

# ---- safetensors, read with numpy (the format is a JSON header + raw little-endian arrays) ----

_DT = {"F32": np.float32, "F16": np.float16, "BF16": None, "I64": np.int64, "F64": np.float64}


def load_safetensors(path: Path) -> dict[str, torch.Tensor]:
    raw = Path(path).read_bytes()
    (n,) = struct.unpack("<Q", raw[:8])
    header = json.loads(raw[8:8 + n])
    body = memoryview(raw)[8 + n:]
    out = {}
    for name, meta in header.items():
        if name == "__metadata__":
            continue
        dt = _DT.get(meta["dtype"])
        if dt is None:
            raise ValueError(f"unsupported dtype {meta['dtype']} in {path.name}")
        a, b = meta["data_offsets"]
        arr = np.frombuffer(body[a:b], dtype=dt).reshape(meta["shape"])
        out[name] = torch.from_numpy(arr.astype(np.float32, copy=True))
    return out


# ---- network ---------------------------------------------------------------------------------

class Conv3XC(nn.Module):
    """Re-parameterisable conv block. Holds the training-time branches (so the checkpoint loads
    as is) and runs as one fused 3x3 convolution."""

    def __init__(self, c_in: int, c_out: int, gain: int = 2, relu: bool = False):
        super().__init__()
        self.has_relu = relu
        self.sk = nn.Conv2d(c_in, c_out, 1)
        self.conv = nn.Sequential(nn.Conv2d(c_in, c_in * gain, 1),
                                  nn.Conv2d(c_in * gain, c_out * gain, 3),
                                  nn.Conv2d(c_out * gain, c_out, 1))
        self.eval_conv = nn.Conv2d(c_in, c_out, 3, padding=1)
        self.fused = False

    @torch.no_grad()
    def fuse(self) -> None:
        w1, b1 = self.conv[0].weight, self.conv[0].bias
        w2, b2 = self.conv[1].weight, self.conv[1].bias
        w3, b3 = self.conv[2].weight, self.conv[2].bias
        w = F.conv2d(w1.flip(2, 3).permute(1, 0, 2, 3), w2, padding=2).flip(2, 3).permute(1, 0, 2, 3)
        b = (w2 * b1.reshape(1, -1, 1, 1)).sum((1, 2, 3)) + b2
        wc = F.conv2d(w.flip(2, 3).permute(1, 0, 2, 3), w3).flip(2, 3).permute(1, 0, 2, 3)
        bc = (w3 * b.reshape(1, -1, 1, 1)).sum((1, 2, 3)) + b3
        self.eval_conv.weight.copy_(wc + F.pad(self.sk.weight, [1, 1, 1, 1]))
        self.eval_conv.bias.copy_(bc + self.sk.bias)
        self.fused = True

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if not self.fused:
            self.fuse()
        out = self.eval_conv(x)
        return F.leaky_relu(out, 0.05) if self.has_relu else out


class SPAB(nn.Module):
    def __init__(self, ch: int):
        super().__init__()
        self.c1_r, self.c2_r, self.c3_r = Conv3XC(ch, ch), Conv3XC(ch, ch), Conv3XC(ch, ch)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        out1 = self.c1_r(x)
        out3 = self.c3_r(F.silu(self.c2_r(F.silu(out1))))
        return (out3 + x) * (torch.sigmoid(out3) - 0.5), out1


class CNNSR(nn.Module):
    def __init__(self, c_in: int = 4, c_out: int = 4, ch: int = 24, upscale: int = 4,
                 blocks: int = 6):
        super().__init__()
        self.conv_1 = Conv3XC(c_in, ch)
        self.blocks = nn.ModuleList(SPAB(ch) for _ in range(blocks))
        self.conv_cat = nn.Conv2d(ch * 4, ch, 1)
        self.conv_2 = Conv3XC(ch, ch)
        self.upsampler = nn.Sequential(nn.Conv2d(ch, c_out * upscale**2, 3, padding=1),
                                       nn.PixelShuffle(upscale))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        feat = self.conv_1(x)
        # As in the published model, every block reads the *initial* features (they aren't
        # chained); the weights were trained this way, so the port keeps it.
        for i, blk in enumerate(self.blocks):
            out, out1 = blk(feat)
            if i == 0:
                out_b1 = out
            last1 = out1
        out = self.conv_cat(torch.cat([feat, self.conv_2(out), out_b1, last1], 1))
        return self.upsampler(out)


class HardConstraint(nn.Module):
    """Low frequencies from the (bicubic-upsampled) input, high frequencies from the network."""

    def __init__(self, low_pass_mask: torch.Tensor):
        super().__init__()
        self.register_buffer("low", low_pass_mask)

    def forward(self, lr: torch.Tensor, sr: torch.Tensor) -> torch.Tensor:
        up = F.interpolate(lr, size=sr.shape[-2:], mode="bicubic", antialias=True)
        f_sr = torch.fft.fftshift(torch.fft.fftn(sr, dim=(-2, -1)), dim=(-2, -1))
        f_lr = torch.fft.fftshift(torch.fft.fftn(up, dim=(-2, -1)), dim=(-2, -1))
        mix = f_lr * self.low + f_sr * (1 - self.low)
        return torch.real(torch.fft.ifft2(torch.fft.ifftshift(mix, dim=(-2, -1))))
