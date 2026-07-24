from pathlib import Path

import numpy as np

from core.image_io import read_image, write_png
from service.project_service import (
    MapSetSaveRequest,
    MapSetUpdateRequest,
    save_mapset_copy,
    save_mapset_in_place,
)


def test_save_mapset_copy_preserves_maps_and_overrides_edited_pixels(tmp_path: Path):
    """A new MapSet must be complete while leaving its source untouched."""
    source = tmp_path / "source"
    source.mkdir()
    albedo = np.full((5, 6, 3), 10, dtype=np.uint8)
    normal = np.full((5, 6, 3), 20, dtype=np.uint8)
    assert write_png(source / "albedo_map.png", albedo)
    assert write_png(source / "normal_map.png", normal)
    edited = np.full((5, 6, 3), 77, dtype=np.uint8)

    saved = save_mapset_copy(
        MapSetSaveRequest(
            destination_root=tmp_path,
            mapset_name="poisson_result",
            maps=(("albedo_map", source / "albedo_map.png"), ("normal_map", source / "normal_map.png")),
            edited_maps=(("albedo_map", edited),),
            label_text="0 0.5 0.5 0.2 0.2\n",
        )
    )

    assert saved.folder == (tmp_path / "poisson_result").resolve()
    assert np.array_equal(read_image(saved.map_paths["albedo_map"]), edited)
    assert np.array_equal(read_image(saved.map_paths["normal_map"]), normal)
    assert np.array_equal(read_image(source / "albedo_map.png"), albedo)
    assert saved.label_path.read_text(encoding="utf-8") == "0 0.5 0.5 0.2 0.2\n"


def test_save_mapset_copy_rejects_existing_destination(tmp_path: Path):
    """Saving must never merge into or overwrite an existing MapSet."""
    destination = tmp_path / "duplicate"
    destination.mkdir()

    request = MapSetSaveRequest(tmp_path, "duplicate", tuple(), tuple(), "")
    try:
        save_mapset_copy(request)
    except FileExistsError:
        pass
    else:
        raise AssertionError("existing MapSet destination was overwritten")


def test_save_mapset_in_place_writes_all_maps_and_labels_as_one_unit(tmp_path: Path):
    """Explicit Save must persist the complete current MapSet snapshot."""
    folder = tmp_path / "sample"
    folder.mkdir()
    albedo_path = folder / "albedo_map.png"
    normal_path = folder / "normal_map.png"
    assert write_png(albedo_path, np.zeros((4, 5, 3), dtype=np.uint8))
    assert write_png(normal_path, np.zeros((4, 5, 3), dtype=np.uint8))
    label_path = folder / "sample.txt"
    label_path.write_text("", encoding="utf-8")

    save_mapset_in_place(
        MapSetUpdateRequest(
            maps=(
                ("albedo_map", albedo_path, np.full((4, 5, 3), 31, dtype=np.uint8)),
                ("normal_map", normal_path, np.full((4, 5, 3), 47, dtype=np.uint8)),
            ),
            label_path=label_path,
            label_text="0 0.5 0.5 0.2 0.2\n",
        )
    )

    assert np.all(read_image(albedo_path) == 31)
    assert np.all(read_image(normal_path) == 47)
    assert label_path.read_text(encoding="utf-8") == "0 0.5 0.5 0.2 0.2\n"
