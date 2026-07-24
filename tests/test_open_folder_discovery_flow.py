from core.mapset import discover_map_sets


def test_first_level_folders_are_mapsets_and_deeper_folders_are_ignored(tmp_path):
	folder1 = tmp_path / "folder1"
	folder2 = tmp_path / "folder2"
	deeper = folder1 / "deeper"
	folder1.mkdir()
	folder2.mkdir()
	deeper.mkdir()
	(folder1 / "map1.png").write_bytes(b"x")
	(folder1 / "map2.png").write_bytes(b"x")
	(deeper / "map3.png").write_bytes(b"x")
	(folder2 / "map1.png").write_bytes(b"x")

	mapsets = discover_map_sets(tmp_path, [], [".png"])

	assert [item.name for item in mapsets] == ["folder1", "folder2"]
	assert [key for key, _path in mapsets[0].maps] == ["map1", "map2"]
	assert [key for key, _path in mapsets[1].maps] == ["map1"]


def test_root_level_images_are_single_image_mapsets(tmp_path):
	(tmp_path / "image1.png").write_bytes(b"x")
	(tmp_path / "image2.png").write_bytes(b"x")

	mapsets = discover_map_sets(tmp_path, [], [".png"])

	assert [item.name for item in mapsets] == ["image1", "image2"]
	assert all(item.maps == (("image", item.reference_path),) for item in mapsets)


def test_root_images_and_first_level_folders_are_both_mapsets(tmp_path):
	folder1 = tmp_path / "folder1"
	folder1.mkdir()
	(tmp_path / "image1.png").write_bytes(b"x")
	(folder1 / "map1.png").write_bytes(b"x")

	mapsets = discover_map_sets(tmp_path, [], [".png"])

	assert {item.name for item in mapsets} == {"image1", "folder1"}


def test_single_image_mapsets_are_detectable_for_dialog_skip(tmp_path):
	(tmp_path / "image1.png").write_bytes(b"x")
	(tmp_path / "image2.png").write_bytes(b"x")

	mapsets = discover_map_sets(tmp_path, [], [".png"])

	assert all(
		len(item.maps) == 1 and item.maps[0][0] == "image" and item.folder == item.maps[0][1]
		for item in mapsets
	)


from dataclasses import replace
from core.mapset import MapSet


def test_map_key_filter_keeps_selected_maps_across_mapsets(tmp_path):
	folder1 = tmp_path / "folder1"
	folder2 = tmp_path / "folder2"
	folder1.mkdir()
	folder2.mkdir()
	mapset1 = MapSet(
		folder1,
		(("albedo_map", folder1 / "albedo.png"), ("normal_map", folder1 / "normal.png")),
		None,
	)
	mapset2 = MapSet(
		folder2,
		(("albedo_map", folder2 / "albedo.png"), ("curvature_map", folder2 / "curvature.png")),
		None,
	)

	filtered = [
		replace(map_set, maps=tuple((key, path) for key, path in map_set.maps if key in {"albedo_map"}))
		for map_set in [mapset1, mapset2]
	]

	assert [[key for key, _path in item.maps] for item in filtered] == [["albedo_map"], ["albedo_map"]]
