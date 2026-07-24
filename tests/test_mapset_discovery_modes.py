from pathlib import Path

from core.mapset import discover_map_sets, mapset_from_image_path


def test_subfolders_are_mapsets_and_missing_maps_are_allowed(tmp_path):
	folder1 = tmp_path / "folder1"
	folder2 = tmp_path / "folder2"
	folder1.mkdir()
	folder2.mkdir()
	(folder1 / "albedo_map.png").write_bytes(b"x")
	(folder1 / "normal_map.png").write_bytes(b"x")
	(folder2 / "albedo_map.png").write_bytes(b"x")

	mapsets = discover_map_sets(
		tmp_path,
		[("albedo_map.png", "albedo_map"), ("normal_map.png", "normal_map")],
		[".png"],
	)

	assert [item.name for item in mapsets] == ["folder1", "folder2"]
	assert dict(mapsets[0].maps).keys() == {"albedo_map", "normal_map"}
	assert dict(mapsets[1].maps).keys() == {"albedo_map"}


def test_root_images_are_single_image_mapsets(tmp_path):
	(tmp_path / "image1.png").write_bytes(b"x")
	(tmp_path / "image2.png").write_bytes(b"x")

	mapsets = discover_map_sets(tmp_path, [], [".png"])

	assert [item.name for item in mapsets] == ["image1", "image2"]
	assert all(item.maps[0][0] == "image" for item in mapsets)
	assert [item.reference_path.name for item in mapsets] == ["image1.png", "image2.png"]


def test_selected_image_becomes_single_image_mapset(tmp_path):
	image = tmp_path / "selected.png"
	label = tmp_path / "selected.txt"
	image.write_bytes(b"x")
	label.write_text("0 0.5 0.5 0.25 0.25\n", encoding="utf-8")

	mapset = mapset_from_image_path(image)

	assert mapset.folder == image.resolve()
	assert mapset.maps == (("image", image.resolve()),)
	assert mapset.label_path == label.resolve()
