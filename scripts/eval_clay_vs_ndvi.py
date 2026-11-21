"""Validate embedding change against an independent signal: NDVI change on the same dates.

ROC-AUC = how well the model's patch distance separates patches where NDVI changed strongly
(|ΔNDVI| > 0.3 on most pixels) from those where it didn't. 0.5 = chance, 1.0 = perfect.
NDVI only sees vegetation change, so a strong model can also flag changes NDVI misses;
this measures agreement on the changes both should see.

    python scripts/eval_clay_vs_ndvi.py tengah 2019-01-01/2019-12-31 2026-01-01/2026-11-20
"""

import sys
from pathlib import Path

import numpy as np
import rasterio

from geoask.tools import investigate
from geoask.tools.embedding_change import embedding_change


def auc(labels: np.ndarray, scores: np.ndarray) -> float:
    order = np.argsort(scores)
    ranks = np.empty(len(scores))
    ranks[order] = np.arange(1, len(scores) + 1)
    npos, nneg = labels.sum(), (~labels).sum()
    return float((ranks[labels].sum() - npos * (npos + 1) / 2) / (npos * nneg))


def main(place: str, t0: str, t1: str, model: str = "clay-v1.5", out: str = "out") -> dict:
    r = embedding_change(place, t0, t1, Path(out), model=model, progress=print)
    nd = investigate.index_change(place, "ndvi", t0, t1, Path(out))
    if (nd["date0"], nd["date1"]) != (r["date0"], r["date1"]):
        raise SystemExit("date selection differed between the two tools")
    with rasterio.open(Path(out) / nd["id"] / "delta.tif") as s:
        dndvi = s.read(1)
    pmap = np.load(Path(out) / r["id"] / "distance_patch.npy")
    step = int(r["patch_m"] / r["grid"]["res_m"])
    labels, scores = [], []
    for i in range(pmap.shape[0]):
        for j in range(pmap.shape[1]):
            blk = dndvi[i * step:(i + 1) * step, j * step:(j + 1) * step]
            if blk.size == 0 or np.isnan(blk).mean() > 0.5 or not np.isfinite(pmap[i, j]):
                continue
            labels.append(np.nanmean(np.abs(blk) > 0.3) > 0.5)
            scores.append(pmap[i, j])
    labels, scores = np.array(labels), np.array(scores)
    res = {"place": place, "dates": [r["date0"], r["date1"]], "model": r["model"],
           "patches": len(labels), "ndvi_changed": int(labels.sum()),
           "roc_auc": round(auc(labels, scores), 3), "changed_ha": r["changed_ha"],
           "ndvi_loss_ha": nd["loss_ha"], "ndvi_gain_ha": nd["gain_ha"]}
    print(res)
    return res


if __name__ == "__main__":
    main(*sys.argv[1:])
