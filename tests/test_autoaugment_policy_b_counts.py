from collections import OrderedDict

from service.augmentation_service import AugmentationApi, AutoYoloAugmentOptions


def test_policy_b_expected_count_uses_train_full_val_deterministic_test_base(tmp_path):
	options = AutoYoloAugmentOptions(
		output_root=tmp_path,
		defect_root=None,
		target_map_key="albedo_map",
		generate_samples=180,
		enable_poisson=True,
		enable_flip=True,
		enable_rotation=True,
		enable_random=True,
		random_multiplier=2,
		rotation_angles=[45, 90, 135, 180, 225, 270, 315],
		train_ratio=0.8,
		val_ratio=0.1,
		test_ratio=0.1,
	)
	grouped_items = OrderedDict({"root": [{} for _ in range(81)]})
	# base = 81 original + 180 poisson = 261
	# split = 208 train / 26 val / 27 test
	# train = 208 * 2 * 7 * 2 = 5824
	# val = 26 * 2 * 7 = 364
	# test = 27
	assert AugmentationApi._estimate_auto_yolo_outputs_by_group(grouped_items, options, True) == 6215
