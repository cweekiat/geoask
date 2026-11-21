"""Minimal Clay v1.5 encoder for inference.

Ported from the Clay Foundation model (https://github.com/Clay-foundation/model, Apache-2.0):
``claymodel/backbone.py``, ``claymodel/factory.py`` (the DOFA-style dynamic embedding),
``claymodel/utils.py`` and the no-masking encoder in ``claymodel/finetune/embedder/factory.py``.
The changes: no Lightning/timm/einops dependencies, no masking, and it returns patch tokens as well
as the CLS embedding. Parameter names match ``model.encoder.*`` in the official checkpoint, so its
weights load unchanged.
"""

from __future__ import annotations

import torch
import torch.nn.functional as F
from torch import nn

# ---- positional encodings (claymodel/utils.py) ---------------------------------------------


def posemb_sincos_2d_with_gsd(h, w, dim, gsd, temperature: int = 10000):
    y, x = torch.meshgrid(torch.arange(h), torch.arange(w), indexing="ij")
    omega = torch.arange(dim // 4) / (dim // 4 - 1)
    omega = 1.0 / (temperature ** (2 * omega / dim)) * (gsd.cpu() / 1.0)
    y = y.flatten()[:, None] * omega[None, :]
    x = x.flatten()[:, None] * omega[None, :]
    return torch.cat((x.sin(), x.cos(), y.sin(), y.cos()), dim=1).float()


def posemb_sincos_1d(waves, dim, temperature: int = 10000):
    omega = torch.arange(dim // 2, device=waves.device) / (dim // 2 - 1)
    omega = 1.0 / (temperature**omega)
    scaled = waves[:, None] * omega[None, :]
    return torch.cat((scaled.sin(), scaled.cos()), dim=1).float()


# ---- transformer (claymodel/backbone.py) -----------------------------------------------------


class FeedForward(nn.Module):
    def __init__(self, dim, hidden_dim):
        super().__init__()
        self.net = nn.Sequential(nn.LayerNorm(dim), nn.Linear(dim, hidden_dim), nn.GELU(),
                                 nn.Linear(hidden_dim, dim))

    def forward(self, x):
        return self.net(x)


class Attention(nn.Module):
    def __init__(self, dim, heads, dim_head):
        super().__init__()
        self.heads = heads
        self.norm = nn.LayerNorm(dim)
        self.to_qkv = nn.Linear(dim, dim_head * heads * 3, bias=False)
        self.to_out = nn.Linear(dim_head * heads, dim, bias=False)

    def forward(self, x):
        b, n, _ = x.shape
        q, k, v = self.to_qkv(self.norm(x)).chunk(3, dim=-1)
        q, k, v = (t.view(b, n, self.heads, -1).transpose(1, 2) for t in (q, k, v))
        x = F.scaled_dot_product_attention(q, k, v, dropout_p=0.0)
        return self.to_out(x.transpose(1, 2).reshape(b, n, -1))


class Transformer(nn.Module):
    def __init__(self, dim, depth, heads, dim_head, mlp_dim):
        super().__init__()
        self.norm = nn.LayerNorm(dim)
        self.layers = nn.ModuleList(
            nn.ModuleList([Attention(dim, heads, dim_head), FeedForward(dim, mlp_dim)])
            for _ in range(depth))

    def forward(self, x):
        for attn, ff in self.layers:
            x = attn(x) + x
            x = ff(x) + x
        return self.norm(x)


# ---- dynamic (wavelength-conditioned) patch embedding (claymodel/factory.py) ------------------


class FCBlock(nn.Module):
    def __init__(self, size):
        super().__init__()
        self.l1 = nn.Linear(size, size)
        self.l2 = nn.Linear(size, size)

    def forward(self, x):
        return x + F.gelu(self.l2(F.gelu(self.l1(x))))


class WavesTransformer(nn.Module):
    def __init__(self, wave_dim, output_dim, num_latent_tokens, embed_dim, num_heads=4):
        super().__init__()
        self.num_latent_tokens = num_latent_tokens
        layer = nn.TransformerEncoderLayer(d_model=wave_dim, nhead=num_heads, activation="gelu",
                                           dropout=0, norm_first=False, batch_first=True)
        self.encoder = nn.TransformerEncoder(layer, 1, enable_nested_tensor=False)
        self.fc_weight = nn.Linear(wave_dim, output_dim)
        self.fc_bias = nn.Linear(wave_dim, embed_dim)
        self.weight_tokens = nn.Parameter(torch.zeros(num_latent_tokens, wave_dim))
        self.bias_token = nn.Parameter(torch.zeros(1, wave_dim))

    def forward(self, x):
        x = torch.cat([self.weight_tokens, x, self.bias_token], dim=0)
        out = self.encoder(x)
        n = self.num_latent_tokens
        weights = self.fc_weight(out[n:-1] + x[n:-1])
        bias = self.fc_bias(out[-1])
        return weights, bias


class DynamicEmbedding(nn.Module):
    def __init__(self, wave_dim, num_latent_tokens, patch_size, embed_dim):
        super().__init__()
        self.wave_dim = wave_dim
        self.patch_size = patch_size
        self.embed_dim = embed_dim
        self.weight_generator = WavesTransformer(wave_dim, patch_size**2 * embed_dim,
                                                 num_latent_tokens, embed_dim)
        self.fclayer = FCBlock(wave_dim)

    def kernel(self, waves: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Generate the conv kernel for a set of band wavelengths (µm). Depends only on waves,
        so it can be computed once per instrument and frozen (that's how the Core ML / ONNX
        exports get a fixed-band model)."""
        w = self.fclayer(posemb_sincos_1d(waves, self.wave_dim))
        weight, bias = self.weight_generator(w)  # [C, (D k k)], [D]
        p = self.patch_size
        weight = weight.view(len(waves), self.embed_dim, p, p).transpose(0, 1)  # [D C k k]
        return weight * 0.02, bias

    def forward(self, cube, waves):
        weight, bias = self.kernel(waves)
        x = F.conv2d(cube, weight, bias=bias, stride=self.patch_size)  # [B D h w]
        return x.flatten(2).transpose(1, 2)  # [B L D]


# ---- encoder -------------------------------------------------------------------------------


class ClayEncoder(nn.Module):
    """Clay v1.5 encoder (large): dim 1024, depth 24, 16 heads, patch 8."""

    def __init__(self, dim=1024, depth=24, heads=16, dim_head=64, mlp_ratio=4.0, patch_size=8):
        super().__init__()
        self.dim = dim
        self.patch_size = patch_size
        self.cls_token = nn.Parameter(torch.zeros(1, 1, dim))
        self.patch_embedding = DynamicEmbedding(128, 128, patch_size, dim)
        self.transformer = Transformer(dim, depth, heads, dim_head, int(dim * mlp_ratio))

    def forward(self, pixels, time, latlon, gsd, waves):
        """pixels [B C H W] normalised; time/latlon [B 4]; gsd [1]; waves [C] µm.
        Returns (cls [B D], patch tokens [B h w D])."""
        b = pixels.shape[0]
        patches = self.patch_embedding(pixels, waves)  # [B L D]
        h = pixels.shape[2] // self.patch_size
        w = pixels.shape[3] // self.patch_size
        pos = posemb_sincos_2d_with_gsd(h, w, self.dim - 8, gsd).to(patches)  # [L D-8]
        meta = torch.cat((time, latlon), dim=1).to(patches)  # [B 8]
        enc = torch.cat((pos.expand(b, -1, -1), meta[:, None, :].expand(-1, h * w, -1)), dim=-1)
        x = torch.cat((self.cls_token.expand(b, -1, -1), patches + enc), dim=1)
        x = self.transformer(x)
        return x[:, 0], x[:, 1:].reshape(b, h, w, self.dim)
