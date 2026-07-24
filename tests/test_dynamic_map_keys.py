from pathlib import Path
from types import SimpleNamespace

from service.augmentation_service import AugmentationApi


def test_project_map_keys_keeps_loaded_order(tmp_path):
	mapsets = [
		SimpleNamespace(maps=(('albedo_map', tmp_path / 'a.png'), ('normal_map', tmp_path / 'n.png'))),
		SimpleNamespace(maps=(('normal_map', tmp_path / 'n2.png'), ('custom_map', tmp_path / 'c.png'))),
	]
	assert AugmentationApi().project_map_keys(mapsets) == ['albedo_map', 'normal_map', 'custom_map']


def test_collect_target_map_patches_uses_selected_map_key(tmp_path):
	defect_root = tmp_path / 'exports' / 'defects'
	class_dir = defect_root / 'scratch'
	class_dir.mkdir(parents=True)
	(class_dir / '0001_albedo_map.png').write_bytes(b'x')
	(class_dir / '0001_albedo_map_mask.png').write_bytes(b'x')
	(class_dir / '0001_normal_map.png').write_bytes(b'x')
	(class_dir / '0001_yolo_result.png').write_bytes(b'x')

	paths = AugmentationApi()._collect_target_map_patches(defect_root, 'albedo_map', tmp_path)
	assert paths == [(class_dir / '0001_albedo_map.png').resolve()]
