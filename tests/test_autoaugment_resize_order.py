from pathlib import Path


def test_auto_yolo_resizes_after_poisson_before_staged_output_augment():
	text = Path("service/augmentation_service.py").read_text(encoding="utf-8")
	poisson_index = text.index("blended = self.poisson_api.poisson_blend")
	resize_index = text.index("resized, labels = self._resize_for_yolo")
	staged_index = text.index("def _iter_staged_samples")
	assert poisson_index < resize_index < staged_index
