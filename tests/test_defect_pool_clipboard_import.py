from pathlib import Path

import cv2
import numpy as np

from core.patch_clipboard import read_defect_pool


def test_read_defect_pool_groups_exported_maps_by_class_and_id(tmp_path: Path):
    """One exported defect must become one aligned multi-map clipboard payload."""
    folder = tmp_path / "Crack"
    folder.mkdir()
    image = np.full((8, 9, 3), 170, dtype=np.uint8)
    mask = np.zeros((8, 9), dtype=np.uint8)
    mask[2:6, 3:7] = 255
    for key in ("albedo_map", "normal_map"):
        assert cv2.imwrite(str(folder / f"0001_{key}.png"), image)
        assert cv2.imwrite(str(folder / f"0001_{key}_mask.png"), mask)

    payloads = read_defect_pool(tmp_path)

    assert len(payloads) == 1
    assert payloads[0]["name"] == "Crack 0001"
    assert set(payloads[0]["maps"]) == {"albedo_map", "normal_map"}
    assert payloads[0]["preview_key"] == "albedo_map"
    assert np.array_equal(payloads[0]["mask"], mask)
