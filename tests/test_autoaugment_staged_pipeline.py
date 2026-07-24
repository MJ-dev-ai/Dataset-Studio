from pathlib import Path


def test_staged_autoaugment_options_are_available():
	text = Path("service/augmentation_service.py").read_text(encoding="utf-8")
	for name in [
		"include_original",
		"enable_poisson",
		"enable_flip",
		"enable_rotation",
		"enable_random",
		"random_multiplier",
	]:
		assert name in text


def test_staged_pipeline_order_and_resize_after_poisson():
	text = Path("service/augmentation_service.py").read_text(encoding="utf-8")
	run = text.index("def run_auto_yolo_augmentation")
	base_call = text.index("base_records = self._build_base_records", run)
	split_call = text.index("split_records = self._split_base_records", run)
	load_call = text.index("sample = self._load_base_record_sample", run)
	write_call = text.index("write_staged(split", load_call)
	assert base_call < split_call < load_call < write_call

	staged = text.index("def _iter_staged_samples")
	flip = text.index("options.enable_flip", staged)
	rotation = text.index("options.enable_rotation", staged)
	random = text.index("options.enable_random", staged)
	assert staged < flip < rotation < random

	blend = text.index("blended = self.poisson_api.poisson_blend")
	resize = text.index("resized, labels = self._resize_for_yolo")
	assert blend < resize


def test_stage_checkboxes_are_in_autoaugment_ui():
	text = Path("ui/autoaugment.ui").read_text(encoding="utf-8")
	assert "Include original images" not in text
	for label in [
		"Horizontal Flip",
		"Rotation",
		"Random x",
		"Cancel",
	]:
		assert label in text


def test_autoaugment_reports_weighted_pipeline_stages():
    text = Path("service/augmentation_service.py").read_text(encoding="utf-8")
    for stage in [
        "Preparing inputs",
        "Generating Poisson samples",
        "Shuffling and splitting dataset",
        "Writing train outputs",
        "Writing val outputs",
        "Writing test outputs",
        "Finalizing dataset",
    ]:
        assert stage in text
