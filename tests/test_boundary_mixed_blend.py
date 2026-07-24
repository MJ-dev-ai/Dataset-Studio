import cv2
import numpy as np

from service.editing_service import PoissonApi


def test_boundary_mixed_preserves_thick_defect_core(monkeypatch):
    """Mixed Clone output must not replace the protected center of a thick defect."""
    api = PoissonApi()
    target = np.full((30, 30, 3), 60, np.uint8)
    patch = np.full((14, 14, 3), 220, np.uint8)
    mask = np.full((14, 14), 255, np.uint8)
    monkeypatch.setattr(api, "seamless_clone", lambda source, target, mask, center, mode: target.copy())

    result = api.boundary_mixed_blend(target, patch, mask, 8, 8, boundary_ratio=0.2)

    assert np.all(result[15, 15] == 124)
    assert np.all(result[8, 8] == 60)


def test_boundary_mixed_retains_centerline_for_thin_crack(monkeypatch):
    """A one-pixel crack must not disappear when ordinary erosion has no core."""
    api = PoissonApi()
    target = np.full((20, 20, 3), 80, np.uint8)
    patch = np.zeros((8, 8, 3), np.uint8)
    patch[:, 4] = 240
    mask = np.zeros((8, 8), np.uint8)
    mask[:, 4] = 255
    monkeypatch.setattr(api, "seamless_clone", lambda source, target, mask, center, mode: target.copy())

    result = api.boundary_mixed_blend(target, patch, mask, 6, 6, boundary_ratio=0.3)

    assert np.all(result[6:14, 10] == 144)


def test_boundary_mixed_uses_mixed_clone_and_ring_mask(monkeypatch):
    """Only a boundary ring, not the full defect mask, should be sent to OpenCV."""
    api = PoissonApi()
    captured = {}

    def fake_clone(source, target, mask, center, mode):
        captured["mask"] = mask.copy()
        captured["mode"] = mode
        return target.copy()

    monkeypatch.setattr(api, "seamless_clone", fake_clone)
    mask = np.zeros((15, 15), np.uint8)
    mask[3:12, 3:12] = 255
    api.boundary_mixed_blend(
        np.zeros((25, 25, 3), np.uint8),
        np.full((15, 15, 3), 180, np.uint8),
        mask,
        5,
        5,
        boundary_ratio=0.2,
    )

    assert captured["mode"] == cv2.MIXED_CLONE
    assert captured["mask"][7, 7] == 0
    assert captured["mask"][2, 7] == 0
    assert captured["mask"][3, 7] == 255


def test_boundary_radius_is_five_percent_of_short_patch_side():
    """Boundary width should scale with patch size instead of using a fixed pixel value."""
    assert PoissonApi.boundary_radius_for_patch((200, 400)) == 10
    assert PoissonApi.boundary_radius_for_patch((20, 100)) == 2
    assert PoissonApi.boundary_radius_for_patch((2000, 1000)) == 50


def test_boundary_mixed_passes_masked_patch_without_alpha(monkeypatch):
    """Poisson source must be a direct masked paste without opacity attenuation."""
    api = PoissonApi()
    target = np.full((30, 30, 3), 160, np.uint8)
    patch = np.full((20, 20, 3), 220, np.uint8)
    patch[[0, -1], :] = 0
    patch[:, [0, -1]] = 0
    mask = np.full((20, 20), 255, np.uint8)
    captured = {}

    def fake_clone(source, target, mask, center, mode):
        captured["source"] = source.copy()
        return target.copy()

    monkeypatch.setattr(api, "seamless_clone", fake_clone)
    api.boundary_mixed_blend(target, patch, mask, 5, 5, boundary_ratio=0.2)

    assert np.all(captured["source"][0, 0] == 0)
    assert np.all(captured["source"][10, 10] == 184)


def test_boundary_mixed_restores_original_pixels_outside_patch_mask(monkeypatch):
    """Even an abnormal clone result must never alter the source image outside the patch mask."""
    api = PoissonApi()
    target = np.full((20, 20, 3), 90, np.uint8)
    patch = np.full((8, 8, 3), 210, np.uint8)
    mask = np.zeros((8, 8), np.uint8)
    mask[2:6, 2:6] = 255
    monkeypatch.setattr(
        api,
        "seamless_clone",
        lambda source, target, mask, center, mode: np.full_like(target, 17),
    )

    result = api.boundary_mixed_blend(target, patch, mask, 6, 6)

    outside_global = np.ones((20, 20), dtype=bool)
    outside_global[8:12, 8:12] = False
    assert np.array_equal(result[outside_global], target[outside_global])


def test_protected_core_keeps_most_of_a_thin_defect():
    """A large patch-relative radius must not turn most thin defect pixels into Poisson pixels."""
    mask = np.zeros((100, 100), np.uint8)
    mask[45:55, 10:90] = 255

    core = PoissonApi._protected_core_mask(mask, erosion_radius=25)

    assert np.count_nonzero(core) >= np.count_nonzero(mask) * 0.6


def test_tone_matching_uses_one_luminance_shift_for_grayscale_patch():
    """Grayscale correction must preserve equal channels while partially matching brightness."""
    patch = np.full((6, 6, 3), 220, np.uint8)
    target = np.full((6, 6, 3), 100, np.uint8)
    mask = np.full((6, 6), 255, np.uint8)

    matched = PoissonApi._match_patch_tone(patch, target, mask, strength=0.6)

    assert np.all(matched == 148)
    assert np.array_equal(matched[:, :, 0], matched[:, :, 1])


def test_tone_matching_uses_channel_offsets_for_color_patch():
    """Color correction must move each channel toward the local target without changing the mask."""
    patch = np.full((5, 5, 3), (220, 80, 30), np.uint8)
    target = np.full((5, 5, 3), (100, 140, 90), np.uint8)
    mask = np.zeros((5, 5), np.uint8)
    mask[1:4, 1:4] = 255

    matched = PoissonApi._match_patch_tone(patch, target, mask, strength=0.6)

    assert np.array_equal(matched[2, 2], np.array([148, 116, 66], np.uint8))
    assert np.array_equal(matched[0, 0], patch[0, 0])
