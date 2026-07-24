import json

import cv2
import pytest

from service.augmentation_service import AutoYoloAugmentOptions, AugmentationApi


def test_class_catalog_maps_defect_folder_names(tmp_path):
    (tmp_path / "labels.json").write_text(
        json.dumps({"labels": [{"class_id": 3, "class_name": "Crack"}]}),
        encoding="utf-8",
    )
    api = AugmentationApi()
    catalog = api._class_catalog(tmp_path)
    assert catalog == {"crack": 3}
    assert api._defect_class_id(tmp_path / "Crack" / "0001_albedo.png", catalog) == 3


@pytest.mark.parametrize(
    ("selected_mode", "expected"),
    [
        ("Mixed", cv2.MIXED_CLONE),
        ("Normal", cv2.NORMAL_CLONE),
    ],
)
def test_autoaugment_uses_selected_poisson_mode(tmp_path, selected_mode, expected):
    options = AutoYoloAugmentOptions(
        output_root=tmp_path / "output",
        defect_root=tmp_path / "defects",
        target_map_key="albedo_map",
        poisson_mode=selected_mode,
    )

    assert AugmentationApi.poisson_clone_mode(options) == expected


def test_autoaugment_rejects_unknown_poisson_mode(tmp_path):
    options = AutoYoloAugmentOptions(
        output_root=tmp_path / "output",
        defect_root=None,
        target_map_key="albedo_map",
        poisson_mode="Unknown",
    )

    with pytest.raises(ValueError, match="Unsupported Poisson clone mode"):
        AugmentationApi.poisson_clone_mode(options)


def test_detail_preserve_is_available_without_an_opencv_clone_mode(tmp_path):
    """Detail-preserving CopyPaste is a composition method, not an OpenCV clone constant."""
    options = AutoYoloAugmentOptions(
        output_root=tmp_path,
        defect_root=tmp_path,
        target_map_key="albedo_map",
        poisson_mode="Detail Preserve",
    )

    assert options.poisson_mode == "Detail Preserve"


def test_boundary_mixed_is_a_selectable_composition_mode(tmp_path):
    """Boundary-only Mixed Clone should travel through the existing mode option."""
    options = AutoYoloAugmentOptions(
        output_root=tmp_path,
        defect_root=tmp_path,
        target_map_key="albedo_map",
        poisson_mode="Boundary Mixed",
    )

    assert options.poisson_mode == "Boundary Mixed"
