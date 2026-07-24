from service.augmentation_service import AugmentationApi, AutoYoloAugmentOptions


def test_poisson_samples_are_global_not_per_mapset(tmp_path):
	options = AutoYoloAugmentOptions(
		output_root=tmp_path,
		defect_root=None,
		target_map_key="albedo_map",
		generate_samples=3,
		enable_poisson=True,
		enable_flip=False,
		enable_rotation=False,
		enable_random=False,
		train_ratio=0.8,
		val_ratio=0.1,
		test_ratio=0.1,
	)
	assert AugmentationApi._estimate_auto_yolo_outputs(81, options, True) == 84
