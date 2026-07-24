import numpy as np

from service.editing_service import PoissonApi


def test_detail_preserve_blend_keeps_thin_defect_contrast():
    """Thin masked defects must remain visible instead of being dissolved like Poisson gradients."""
    target = np.full((12, 12, 3), 100, dtype=np.uint8)
    patch = np.zeros((5, 5, 3), dtype=np.uint8)
    patch[:, 2] = 240
    mask = np.zeros((5, 5), dtype=np.uint8)
    mask[:, 2] = 255

    result = PoissonApi().detail_preserve_blend(target, patch, mask, 3, 3)

    assert np.all(result[3:8, 5] >= 125)
    assert np.all(result[3:8, 4] == 100)


def test_detail_preserve_blend_does_not_modify_pixels_outside_mask():
    """Feathering must never leak the patch's black background into the target."""
    target = np.full((10, 10, 3), 120, dtype=np.uint8)
    patch = np.zeros((4, 4, 3), dtype=np.uint8)
    patch[1:3, 1:3] = 220
    mask = np.zeros((4, 4), dtype=np.uint8)
    mask[1:3, 1:3] = 255

    result = PoissonApi().detail_preserve_blend(target, patch, mask, 2, 2)

    assert np.all(result[2, 2] == 120)
    assert np.all(result[3:5, 3:5] > 140)


def test_detail_preserve_adapts_bright_patch_to_dark_target():
    """A bright donor defect should retain contrast without floating like a white sticker."""
    target = np.full((12, 12, 3), 20, dtype=np.uint8)
    patch = np.full((5, 5, 3), 230, dtype=np.uint8)
    patch[2, :] = 255
    mask = np.full((5, 5), 255, dtype=np.uint8)

    result = PoissonApi().detail_preserve_blend(target, patch, mask, 3, 3)

    assert 40 <= int(result[4, 4, 0]) <= 100
    assert int(result[5, 5, 0]) > int(result[4, 4, 0])


def test_detail_preserve_skips_color_adaptation_for_normal_maps():
    """Normal-map vectors must not be shifted toward the target's local channel median."""
    target = np.full((8, 8, 3), 20, dtype=np.uint8)
    patch = np.full((4, 4, 3), 220, dtype=np.uint8)
    mask = np.full((4, 4), 255, dtype=np.uint8)

    result = PoissonApi().detail_preserve_blend(target, patch, mask, 2, 2, adapt_color=False)

    assert int(result[3, 3, 0]) >= 150
