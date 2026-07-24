from pathlib import Path

import numpy as np

from core.patch_clipboard import PatchClipboard


def test_patch_clipboard_keeps_multiple_owned_patches():
    """Adding another patch must not replace or alias an existing clip."""
    clipboard = PatchClipboard()
    image = np.full((4, 5, 3), 20, dtype=np.uint8)
    mask = np.full((4, 5), 255, dtype=np.uint8)

    first = clipboard.add(image, mask, "First", Path("source_a.png"))
    image[:] = 99
    second = clipboard.add(image, mask, "Second", Path("source_b.png"))

    assert len(clipboard) == 2
    assert first.clip_id != second.clip_id
    assert np.all(clipboard.get(first.clip_id).image == 20)
    assert np.all(clipboard.get(second.clip_id).image == 99)


def test_patch_clipboard_remove_does_not_renumber_other_clips():
    """Stable IDs are required while Qt drag MIME data is in flight."""
    clipboard = PatchClipboard()
    image = np.ones((2, 2, 3), dtype=np.uint8)
    mask = np.ones((2, 2), dtype=np.uint8)
    first = clipboard.add(image, mask, "A")
    second = clipboard.add(image, mask, "B")

    assert clipboard.remove(first.clip_id)
    assert clipboard.get(first.clip_id) is None
    assert clipboard.get(second.clip_id) is second


def test_mapset_clip_keeps_corresponding_patch_for_every_map_key():
    """One clipboard item must carry aligned source patches for the whole MapSet."""
    clipboard = PatchClipboard()
    mask = np.full((3, 4), 255, dtype=np.uint8)
    albedo = np.full((3, 4, 3), 10, dtype=np.uint8)
    normal = np.full((3, 4, 3), 20, dtype=np.uint8)

    clip = clipboard.add_mapset(
        {"albedo_map": albedo, "normal_map": normal},
        mask,
        "MapSet Patch",
        preview_key="albedo_map",
    )

    assert clip.map_keys == ("albedo_map", "normal_map")
    assert np.array_equal(clip.image_for("normal_map"), normal)
    assert np.array_equal(clip.image, albedo)
