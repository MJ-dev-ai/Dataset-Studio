"""Exercise real augmentation output through the service and UI worker paths."""
from types import SimpleNamespace
from pathlib import Path

import numpy as np
import pytest

from core.image_io import read_image, write_png
from core.mapset import MapSet, ROI_CONTOUR_KEY
from service import augmentation_service as augment
from service.labeling_service import YoloLabel, load_txt
from worker.augmentation_worker import AugmentationWorker


@pytest.mark.parametrize("labels", [[], [YoloLabel(1, 0.25, 0.5, 0.125, 0.25)]])
def test_write_sample_preserves_image_and_yolo_labels(tmp_path, labels):
    """Both annotated and negative samples produce paired UTF-8 label files."""
    options = augment.AutoYoloAugmentOptions(tmp_path, None, "albedo_map")
    (tmp_path / "images/train").mkdir(parents=True)
    (tmp_path / "labels/train").mkdir(parents=True)
    image = np.arange(24 * 32 * 3, dtype=np.uint8).reshape(24, 32, 3)
    image_path, label_path = augment.write_auto_yolo_sample(options, "train", "한글 샘플", image, labels)
    assert image_path.stem == label_path.stem
    np.testing.assert_array_equal(read_image(image_path), image)
    assert load_txt(label_path) == labels
    if not labels:
        assert label_path.read_text(encoding="utf-8") == ""


@pytest.mark.parametrize("entrypoint", ["service", "worker"])
@pytest.mark.parametrize("poisson", [False, True])
def test_autoaugment_finishes_and_writes_complete_dataset(tmp_path, entrypoint, poisson):
    """Run small real compositions and staged transforms through final dataset saving."""
    source = tmp_path / "원본"
    source.mkdir()
    image_path = source / "albedo_map.png"
    label_path = source / "원본.txt"
    image = np.full((128, 128, 3), 100, np.uint8)
    assert write_png(image_path, image)
    label_path.write_text("1 0.25 0.25 0.125 0.125\n", encoding="utf-8")
    contour = ((8.0, 8.0), (120.0, 8.0), (120.0, 120.0), (8.0, 120.0))
    mapset = MapSet(source, (("albedo_map", image_path),), label_path, ((ROI_CONTOUR_KEY, (contour,)),))
    project = SimpleNamespace(root_path=tmp_path, mapsets=[mapset])
    patches = tmp_path / "결함"
    patches.mkdir()
    patch = np.full((16, 16, 3), 160, np.uint8)
    patch[5:11, 5:11] = 220
    assert write_png(patches / "patch_albedo_map.png", patch)
    options = augment.AutoYoloAugmentOptions(
        output_root=tmp_path / "결과", defect_root=patches, target_map_key="albedo_map",
        class_names=["결함", "기존 라벨"], generate_samples=1, enable_poisson=poisson,
        poisson_mode="Boundary Mixed", enable_flip=True, enable_rotation=True,
        rotation_angles=[0, 90], enable_random=False, image_size=128,
        train_ratio=1.0, val_ratio=0.0, test_ratio=0.0, seed=7,
    )
    if entrypoint == "service":
        result = augment.run_auto_yolo_augmentation(project, options)
    else:
        worker = AugmentationWorker("test-export", "auto_augment", {"project": project, "options": options})
        results, failures, finished = [], [], []
        worker.succeeded.connect(lambda _id, value: results.append(value))
        worker.failed.connect(lambda _id, message, trace: failures.append((message, trace)))
        worker.finished.connect(finished.append)
        worker._execute_auto_augment()
        assert not failures, failures
        assert finished == ["test-export"] and not worker.flag.is_running
        assert len(results) == 1
        result = results[0]
    expected = 8 if poisson else 4
    assert result["images"] == result["labels"] == expected
    assert result["poisson_samples"] == int(poisson)
    assert result["failed_or_skipped"] == 0
    run_root = Path(result["output_root"])
    assert run_root.parent == options.output_root.resolve()
    images = sorted((run_root / "images/train").glob("*.png"))
    labels = sorted((run_root / "labels/train").glob("*.txt"))
    assert len(images) == len(labels) == expected
    assert [path.stem for path in images] == [path.stem for path in labels]
    for path in images:
        assert read_image(path).shape == (128, 128, 3)
    annotations = [label for path in labels for label in load_txt(path)]
    assert len(annotations) == result["annotations"] == (12 if poisson else 4)
    assert all(0 <= value <= 1 for label in annotations for value in (label.x_center, label.y_center, label.width, label.height))
    assert "기존 라벨" in (run_root / "data.yaml").read_text(encoding="utf-8")
    assert not (run_root / "_autoaugment_base_cache/poisson").exists()


def test_orientation_transform_keeps_pixels_and_labels_aligned():
    """The other augmentation entrypoint also accepts ordinary function arguments."""
    image = np.arange(16 * 16 * 3, dtype=np.uint8).reshape(16, 16, 3)
    result = augment.transform_mapset_orientation({"albedo_map": image}, [(0.25, 0.5, 0.125, 0.25)], [1], 0, 1, False)
    np.testing.assert_array_equal(result.images["albedo_map"], image[:, ::-1])
    assert result.class_ids == [1]
    assert result.bboxes[0] == pytest.approx((0.75, 0.5, 0.125, 0.25))
