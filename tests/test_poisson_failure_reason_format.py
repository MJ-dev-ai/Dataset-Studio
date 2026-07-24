from collections import Counter

from service.augmentation_service import AugmentationApi


def test_poisson_failure_debug_message_contains_generated_attempts_and_reasons():
	message = AugmentationApi._format_poisson_debug_message(
		"Poisson attempt",
		10,
		30,
		2,
		5,
		Counter({"roi_missing": 3, "placement_failed": 2}),
	)
	assert "generated 2/5" in message
	assert "attempts 10/30" in message
	assert "roi_missing=3" in message
	assert "placement_failed=2" in message
