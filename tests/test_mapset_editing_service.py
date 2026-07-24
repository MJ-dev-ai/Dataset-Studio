import numpy as np

from service.editing_service import (
	apply_healing_to_images,
	apply_healing_strokes,
	apply_paint_strokes,
	apply_selection_delete,
	apply_selection_fill,
)


def test_selection_fill_uses_same_mask_on_any_map_image():
	image = np.zeros((4, 4, 3), dtype=np.uint8)
	mask = np.zeros((4, 4), dtype=np.uint8)
	mask[1:3, 1:3] = 255

	result = apply_selection_fill(image, mask, (10, 20, 30))

	assert result[0, 0].tolist() == [0, 0, 0]
	assert result[1, 1].tolist() == [10, 20, 30]


def test_selection_delete_clears_only_masked_pixels():
	image = np.full((4, 4, 3), 100, dtype=np.uint8)
	mask = np.zeros((4, 4), dtype=np.uint8)
	mask[0, 0] = 255

	result = apply_selection_delete(image, mask)

	assert result[0, 0].tolist() == [0, 0, 0]
	assert result[1, 1].tolist() == [100, 100, 100]


def test_paint_strokes_replay_coordinate_operations():
	image = np.zeros((5, 5, 3), dtype=np.uint8)

	result = apply_paint_strokes(image, [((0, 0), (4, 4))], (255, 0, 0), 1)

	assert result[0, 0, 0] == 255
	assert result[4, 4, 0] == 255


def test_healing_strokes_reconstruct_target_source_difference():
	image = np.full((50, 50, 3), 120, dtype=np.uint8)
	image[25, 18:34] = 20

	result = apply_healing_strokes(
		image,
		[((10, 10), (10, 10), (26, 25), (26, 25))],
		size=14,
		opacity=1.0,
	)

	assert result[25, 26, 0] > image[25, 26, 0]
	assert result[25, 26, 1] > image[25, 26, 1]
	assert result[25, 26, 2] > image[25, 26, 2]


def test_healing_to_images_reports_and_returns_keyed_results():
	image = np.full((50, 50, 3), 120, dtype=np.uint8)
	image[25, 18:34] = 20
	images = {"normal": image, "thermal": image.copy()}
	progress = []

	results = apply_healing_to_images(
		images,
		[((10, 10), (10, 10), (26, 25), (26, 25))],
		size=14,
		opacity=1.0,
		progress=lambda completed, total, key: progress.append((completed, total, key)),
	)

	assert set(results) == {"normal", "thermal"}
	assert progress == [(1, 2, "normal"), (2, 2, "thermal")]
	assert results["normal"][25, 26, 0] > images["normal"][25, 26, 0]


def test_fast_healing_preview_uses_lightweight_composite():
	image = np.full((50, 50, 3), 120, dtype=np.uint8)
	image[25, 18:34] = 20

	result = apply_healing_strokes(
		image,
		[((10, 10), (10, 10), (26, 25), (26, 25))],
		size=14,
		opacity=1.0,
		fast_preview=True,
	)

	assert result[25, 26, 0] > image[25, 26, 0]
