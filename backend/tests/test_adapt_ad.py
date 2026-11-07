"""The safe fallback that fits an ad to a surface (backend/pipeline/adapt_ad.py)."""
import sys
from pathlib import Path

import pytest

cv2 = pytest.importorskip("cv2")
import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from adapt_ad import cover_crop_share, fit_to_aspect  # noqa: E402


def ad_with_markers(w: int, h: int) -> np.ndarray:
    """Flat ad with a red block at the left edge (brand name) and a blue one at the right (price)."""
    img = np.full((h, w, 3), 230, np.uint8)
    img[h // 3: 2 * h // 3, : w // 8] = (0, 0, 255)
    img[h // 3: 2 * h // 3, -w // 8:] = (255, 0, 0)
    return img


def has(img, bgr) -> bool:
    return bool((np.abs(img.astype(int) - bgr).sum(axis=2) < 60).any())


def test_close_formats_still_fill_the_surface():
    ad = ad_with_markers(600, 800)                        # 0.75 ad on a 0.78 poster
    assert cover_crop_share(ad, 0.78) == 0
    out = fit_to_aspect(ad, 0.78)
    assert abs(out.shape[1] / out.shape[0] - 0.78) < 0.01
    assert has(out, (0, 0, 255)) and has(out, (255, 0, 0))


def test_wide_ad_on_tall_poster_is_not_cropped():
    ad = ad_with_markers(1200, 600)                       # 2:1 ad on a 0.78 poster: cover would cut 55%
    assert cover_crop_share(ad, 0.78) > 0.5
    out = fit_to_aspect(ad, 0.78)
    assert abs(out.shape[1] / out.shape[0] - 0.78) < 0.01
    assert has(out, (0, 0, 255)) and has(out, (255, 0, 0))   # brand name AND price still on it
