"""Small on-disk cache for window reads, capped in size and evicted oldest-first.

Raw scenes are never stored. Only the pixels for the area you asked about, on your grid.
"""

from __future__ import annotations

import hashlib
import os
import threading
import uuid
from pathlib import Path

import numpy as np

DEFAULT_DIR = Path(os.environ.get("GEOASK_CACHE", Path.home() / ".cache" / "geoask"))
DEFAULT_CAP_MB = int(os.environ.get("GEOASK_CACHE_MB", "500"))
_evict_lock = threading.Lock()


class WindowCache:
    def __init__(self, root: Path = DEFAULT_DIR, cap_mb: int = DEFAULT_CAP_MB):
        self.root = Path(root)
        self.cap = cap_mb * 1024 * 1024
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.root / (hashlib.sha1(key.encode()).hexdigest() + ".npy")

    def get(self, key: str) -> np.ndarray | None:
        p = self._path(key)
        if not p.exists():
            return None
        os.utime(p)  # mark as recently used
        return np.load(p, allow_pickle=False)

    def put(self, key: str, arr: np.ndarray) -> None:
        """Thread-safe: unique temp file (not matched by the eviction glob), atomic rename."""
        p = self._path(key)
        tmp = p.with_name(f"{p.stem}.{uuid.uuid4().hex}.part")
        with open(tmp, "wb") as f:
            np.save(f, arr, allow_pickle=False)
        tmp.replace(p)
        with _evict_lock:
            self._evict()

    def size_bytes(self) -> int:
        return sum(f.stat().st_size for f in self.root.glob("*.npy"))

    def _evict(self) -> None:
        entries = []
        for f in self.root.glob("*.npy"):
            try:
                st = f.stat()
            except FileNotFoundError:  # removed by another process meanwhile
                continue
            entries.append((st.st_mtime, st.st_size, f))
        entries.sort()
        total = sum(e[1] for e in entries)
        for _mtime, size, f in entries:
            if total <= self.cap:
                break
            f.unlink(missing_ok=True)
            total -= size

    def clear(self) -> None:
        for f in self.root.glob("*.npy"):
            f.unlink(missing_ok=True)
