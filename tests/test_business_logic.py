import numpy as np
import pytest
import cv2

from service.editing_service import PoissonApi, clone_mode_from_text
from service.labeling_service import YoloApi, YoloLabel


def test_compose_patch_rejects_out_of_bounds_placement():
    target = np.zeros((10, 10, 3), dtype=np.uint8)
    patch = np.ones((5, 5, 3), dtype=np.uint8)
    mask = np.full((5, 5), 255, dtype=np.uint8)
    with pytest.raises(ValueError, match="outside"):
        PoissonApi().compose_patch(target, patch, mask, 8, 8)


def test_auto_label_threshold_finds_foreground_box():
    image = np.zeros((20, 30, 3), dtype=np.uint8)
    image[5:15, 10:20] = 255
    labels = YoloApi().auto_label_from_threshold(image, 4)
    assert len(labels) == 1
    assert labels[0].class_id == 4


def test_yolo_api_saves_and_reads_valid_label_lines(tmp_path):
    """YOLO export needs saved labels to be readable from a YoloApi instance."""
    label_path = tmp_path / "labels.txt"
    api = YoloApi()

    api.save_txt(label_path, [YoloLabel(2, 0.1, 0.2, 0.3, 0.4)])

    assert api.read_valid_lines(label_path) == [
        "2 0.100000 0.200000 0.300000 0.400000"
    ]
    assert api.read_valid_lines(tmp_path / "missing.txt") == []


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Normal", cv2.NORMAL_CLONE),
        ("normal clone", cv2.NORMAL_CLONE),
        ("Mixed", cv2.MIXED_CLONE),
        ("MIXED_CLONE", cv2.MIXED_CLONE),
    ],
)
def test_clone_mode_from_text_maps_ui_labels(label, expected):
    assert clone_mode_from_text(label) == expected


def test_clone_mode_from_text_rejects_unknown_mode():
    with pytest.raises(ValueError, match="Unsupported Poisson clone mode"):
        clone_mode_from_text("Monochrome")


def test_manual_poisson_can_disable_silent_hard_paste(monkeypatch):
    """Manual edits must report clone failure instead of pretending a hard paste succeeded."""
    api = PoissonApi()
    target = np.zeros((20, 20, 3), dtype=np.uint8)
    patch = np.ones((5, 5, 3), dtype=np.uint8)
    mask = np.full((5, 5), 255, dtype=np.uint8)

    def fail(*args, **kwargs):
        raise ValueError("forced failure")

    monkeypatch.setattr(api, "seamless_clone", fail)
    with pytest.raises(RuntimeError, match="seamlessClone failed"):
        api.compose_patch(target, patch, mask, 5, 5, fallback=False)
