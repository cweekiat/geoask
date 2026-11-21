from concurrent.futures import ThreadPoolExecutor

import numpy as np

from geoask.data.cache import WindowCache


def test_parallel_puts_and_cap(tmp_path):
    c = WindowCache(tmp_path, cap_mb=1)
    arr = np.zeros((256, 256), np.float32)  # 256 KB each
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(lambda i: c.put(f"k{i}", arr), range(24)))
    assert c.size_bytes() <= 1024 * 1024
    assert not list(tmp_path.glob("*.part"))
