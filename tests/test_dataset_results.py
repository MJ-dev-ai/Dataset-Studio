"""Regressions for lossless export, durable reports and the result inspection UI."""
import json
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit, QLabel, QTableWidget, QScrollArea

from core.image_io import read_image, write_png
from core.mapset import MapSet, ROI_CONTOUR_KEY
from service import dataset_output as output
from service.augmentation_service import AutoYoloAugmentOptions, run_auto_yolo_augmentation
from service.yolo_export_service import YoloExportOptions, export_dataset, split_train_val_test, validate_export
from ui.dataset_result_dialog import DatasetResultSummary, open_result_folder
from ui import dataset_result_dialog as result_ui
from ui.themes import configure_application_font, theme_stylesheet
from worker.base_worker import WorkerCancelled


def make_sources(root, count=3, class_id=5):
    """Create different originals with deliberately identical folder and image names."""
    items = []
    for index in range(count):
        folder = root / str(index) / "동일 이름"
        folder.mkdir(parents=True)
        image_path = folder / "albedo.png"
        assert write_png(image_path, np.full((64, 64, 3), 80 + index * 10, np.uint8))
        label_path = folder / "labels.txt"
        label_path.write_text(f"{class_id} 0.25 0.25 0.125 0.125\n", encoding="utf-8")
        contour = ((3.0, 3.0), (60.0, 3.0), (60.0, 60.0), (3.0, 60.0))
        items.append(MapSet(folder, (("albedo_map", image_path),), label_path, ((ROI_CONTOUR_KEY, (contour,)),)))
    return items


def export_options(root):
    return YoloExportOptions(root, ["표면: 균열", "찍힘"], train_ratio=1, val_ratio=0, class_ids=[2, 5])


@pytest.mark.parametrize("count", [0, 1, 3, 87])
def test_split_accounts_for_every_source(count, tmp_path):
    items = list(range(count))
    options = YoloExportOptions(tmp_path, ["class0"])
    splits = split_train_val_test(items, options)
    assert sorted(item for values in splits.values() for item in values) == items
    assert not splits["test"]
    assert splits == split_train_val_test(items, options)


@pytest.mark.parametrize("ratios", [(0, 0, 0), (-1, 1, 1), (float("nan"), 1, 0)])
def test_invalid_ratios_are_rejected(ratios):
    with pytest.raises(ValueError):
        output.split_groups([1, 2, 3], ratios, 0)


def test_duplicate_names_and_reruns_never_overwrite(tmp_path):
    items = make_sources(tmp_path / "sources")
    base = tmp_path / "선택한 저장 폴더"
    base.mkdir()
    sentinel = base / "기존 파일.txt"
    sentinel.write_text("보존", encoding="utf-8")
    options = export_options(base)
    first, second = export_dataset(items, options), export_dataset(items, options)
    assert first["output_root"] != second["output_root"]
    assert sentinel.read_text(encoding="utf-8") == "보존"
    for result in (first, second):
        root = Path(result["output_root"])
        assert root.parent == base.resolve()
        assert "seed0" in root.name and "split1-0-0" in root.name
        assert result["status"] == "complete"
        assert result["images"] == result["labels"] == result["annotations"] == 3
        assert len({entry["image"] for entry in result["entries"]}) == 3
        assert {int(read_image(root / entry["image"])[0, 0, 0]) for entry in result["entries"]} == {80, 90, 100}
        assert all(output.read_labels(root / entry["label"])[0].class_id == 1 for entry in result["entries"])
        assert validate_export(root)
        manifest = json.loads((root / "run.json").read_text(encoding="utf-8"))
        assert manifest["settings"]["class_ids"] == [2, 5]
        assert manifest["class_mapping"] == {"2": 0, "5": 1}
        yaml = next(root.rglob("data.yaml")).read_text(encoding="utf-8")
        assert '0: "표면: 균열"' in yaml and "test:" not in yaml


@pytest.mark.parametrize("bad_line", ["broken", "7 0.5 0.5 0.1 0.1", "5 nan 0.5 0.1 0.1", "5 0.5 0.5 0 0.1", "5 0.01 0.5 0.5 0.2"])
def test_bad_labels_are_reported_without_silent_drops(tmp_path, bad_line):
    items = make_sources(tmp_path / "source", 2)
    items[0].label_path.write_text(bad_line, encoding="utf-8")
    result = export_dataset(items, export_options(tmp_path / "out"))
    assert result["status"] == "partial" and result["failed"] == 1
    assert result["images"] == 1 and result["issues"][0]["reason"]


@pytest.mark.parametrize("class_id", [0, 99])
def test_saved_file_validation_detects_corruption(tmp_path, class_id):
    result = export_dataset(make_sources(tmp_path / "source", 1), export_options(tmp_path / "out"))
    root = Path(result["output_root"])
    (root / result["entries"][0]["label"]).write_text(f"{class_id} 0.5 0.5 0.1 0.1", encoding="utf-8")
    assert not validate_export(root)


@pytest.mark.parametrize("content", ["[]", "[invalid", "null"])
def test_saved_file_validation_rejects_invalid_yaml(tmp_path, content):
    result = export_dataset(make_sources(tmp_path / "source", 1), export_options(tmp_path / "out"))
    root = Path(result["output_root"])
    next(root.rglob("data.yaml")).write_text(content, encoding="utf-8")
    assert not validate_export(root)


def test_failed_image_write_removes_incomplete_pair(tmp_path, monkeypatch):
    image, label = tmp_path / "images" / "sample.png", tmp_path / "labels" / "sample.txt"
    def fail_write(path, pixels):
        path.write_bytes(b"incomplete")
        return False
    monkeypatch.setattr(output, "write_png", fail_write)
    with pytest.raises(OSError):
        output.write_pair(image, label, np.zeros((8, 8, 3), np.uint8), [])
    assert not image.exists() and not label.exists()


def test_safe_names_preserve_korean_and_remove_windows_reserved_characters():
    assert output.safe_name('한글 설정: */?"<>|') == "한글_설정"
    assert output.safe_name("CON.txt") == "_CON.txt"
    assert output.safe_name("...") == "sample"


def test_cancel_keeps_inspectable_partial_run(tmp_path):
    items = make_sources(tmp_path / "source", 3)
    options = export_options(tmp_path / "out")
    def progress(done, total, message):
        if done >= 1:
            raise WorkerCancelled()
    with pytest.raises(WorkerCancelled):
        export_dataset(items, options, progress_callback=progress)
    report = json.loads(next(options.output_root.rglob("run.json")).read_text(encoding="utf-8"))
    assert report["status"] == "interrupted" and report["images"] == 1
    assert output.validate_run(report)


def test_augmentation_preserves_source_groups_settings_and_reports(tmp_path):
    items = make_sources(tmp_path / "source", 5, class_id=1)
    patches = tmp_path / "patches" / "Stain"
    patches.mkdir(parents=True)
    assert write_png(patches / "defect_albedo_map.png", np.full((8, 8, 3), 200, np.uint8))
    options = AutoYoloAugmentOptions(tmp_path / "out", patches, "albedo_map", ["Scratch", "Dent", "Crack", "Stain"], generate_samples=3, enable_flip=True, enable_rotation=False, enable_random=False, image_size=64, train_ratio=0.6, val_ratio=0.2, test_ratio=0.2)
    result = run_auto_yolo_augmentation(SimpleNamespace(root_path=tmp_path, mapsets=items), options)
    assert result["requested_poisson"] == result["poisson_samples"] == 3
    assert result["generation_diagnostics"]["successful"] == 3
    assert result["status"] == "complete"
    assert result["class_names"] == ["Scratch", "Dent", "Crack", "Stain"]
    assert all(3 in entry["classes"] for entry in result["entries"] if entry["kind"] == "poisson")
    assert options.output_root == tmp_path / "out" and options.generate_samples == 3
    groups = {}
    for entry in result["entries"]:
        groups.setdefault(entry["source_id"], set()).add(entry["split"])
    assert len(groups) == 5 and all(len(value) == 1 for value in groups.values())
    assert {value for values in groups.values() for value in values} == {"train", "val", "test"}
    assert output.validate_run(result)


def test_missing_patches_are_counted_as_unfulfilled_requests(tmp_path):
    items = make_sources(tmp_path / "source", 1, class_id=0)
    options = AutoYoloAugmentOptions(tmp_path / "out", None, "albedo_map", ["결함"], generate_samples=4, enable_flip=False, enable_rotation=False, enable_random=False, image_size=64, train_ratio=1, val_ratio=0, test_ratio=0)
    result = run_auto_yolo_augmentation(SimpleNamespace(root_path=tmp_path, mapsets=items), options)
    assert result["status"] == "partial"
    assert result["images"] == 1 and result["poisson_samples"] == 0
    assert result["skipped"] == 4 and result["failed"] == 0
    assert result["issues"][0]["count"] == 4


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


def test_result_summary_keeps_totals_classes_and_representative_images(tmp_path, app):
    result = export_dataset(make_sources(tmp_path / "source", 2), export_options(tmp_path / "out"))
    result["class_names"] += [f"추가 {index}" for index in range(6)]
    summary = DatasetResultSummary()
    summary.resize(980, 600)
    summary.show()
    summary.set_result(result)
    for _ in range(200):
        QTest.qWait(10)
        if not summary._tasks:
            break
    assert not summary._tasks
    assert not summary.previews[0].pixmap.isNull()
    assert not summary.previews[1].pixmap.isNull()
    assert not summary.preview_tiles[2].isVisible()
    assert len(summary.chart.names) == 8
    assert summary.metric_values["images"].text() == "2"
    assert summary.metric_values["annotations"].text() == "2"
    assert summary.chart.counts == {1: 2}
    assert summary.chart.splits == {"train": 2}
    assert summary.result["settings"]["class_ids"] == [2, 5]
    assert not summary.findChildren(QLineEdit)
    assert not summary.findChildren(QComboBox)
    assert not summary.findChildren(QTableWidget)
    assert not summary.findChildren(QScrollArea)
    visible_text = " ".join(label.text() for label in summary.findChildren(QLabel))
    assert Path(result["entries"][0]["image"]).name not in visible_text
    summary.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_augmentation_summary_uses_composite_examples_and_preserves_failed_counts(tmp_path, app):
    result = export_dataset(make_sources(tmp_path / "source", 7), export_options(tmp_path / "out"))
    result.update(kind="augment", status="partial", failed=2, skipped=3, poisson_samples=3, requested_poisson=6)
    for entry in result["entries"][4:]:
        entry["kind"] = "poisson"
    result["class_names"] += [f"추가 {index}" for index in range(12)]
    summary = DatasetResultSummary()
    summary.resize(980, 600)
    summary.show()
    summary.set_result(result)
    for _ in range(200):
        QTest.qWait(10)
        if not summary._tasks:
            break
    assert summary.metric_values["poisson"].text() == "3 / 6"
    assert summary.metric_values["issues"].text() == "2 / 3"
    assert summary.examples_title.text() == "대표 합성 결과"
    assert "원본 기반 출력 4장 · 합성 기반 출력 3장" == summary.output_summary.text()
    assert all(not preview.pixmap.isNull() for preview in summary.previews[:3])
    assert not summary.preview_tiles[3].isVisible()
    assert all(caption.text().startswith("합성 예시") for caption in summary.preview_captions)
    expected = read_image(Path(result["output_root"]) / result["entries"][4]["image"])[0, 0, 0]
    assert summary.previews[0].pixmap.toImage().pixelColor(0, 0).red() == expected
    assert "생성되지 않은 결과" in summary.status_note.text()
    assert summary.rect().contains(summary.open_button.mapTo(summary, summary.open_button.rect().bottomRight()))
    summary.next_classes.click()
    summary.next_classes.click()
    assert summary.chart.page == 2 and not summary.next_classes.isEnabled()
    assert len(summary.chart.names) == 14
    summary.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.mark.parametrize("count", [0, 3, 4, 28])
def test_fourth_result_image_has_translucent_remaining_count(tmp_path, app, count):
    """Count saved composite outputs, retain the fourth image, and fit a narrow panel."""
    configure_application_font(app)
    image = tmp_path / "합성.png"
    write_png(image, np.full((64, 64, 3), (30, 80, 200), np.uint8))
    summary = DatasetResultSummary(compact=True)
    summary.setStyleSheet(theme_stylesheet("light"))
    summary.resize(358, 606)
    summary.show()
    result = {"output_root": str(tmp_path), "entries": [{"kind": "poisson", "image": image.name} for _ in range(count)]}
    summary.set_result(result)
    for _ in range(200):
        QTest.qWait(10)
        if not summary._tasks:
            break
    assert not summary._tasks
    assert summary.width() == 358
    last = summary.previews[3]
    assert summary.preview_tiles[3].isVisible() == (count > 3)
    assert last.remaining == max(0, count - 3)
    if count > 3:
        assert not last.pixmap.isNull()
        assert last.pixmap.toImage() == summary.previews[0].pixmap.toImage()
        assert last.grab().toImage().pixelColor(5, 5) != summary.previews[0].grab().toImage().pixelColor(5, 5)
        assert summary.rect().contains(last.mapTo(summary, last.rect().bottomRight()))
        summary.set_result({"entries": []})
        assert last.remaining == 0 and last.pixmap.isNull()
        assert summary.preview_tiles[3].isHidden()
    summary.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.mark.skipif(os.name != "nt", reason="Windows folder dispatch")
def test_open_folder_dispatches_actual_run_and_surfaces_errors(tmp_path, app, monkeypatch):
    called, warnings = [], []
    monkeypatch.setattr(os, "startfile", called.append)
    assert open_result_folder(None, tmp_path)
    assert called == [str(tmp_path.resolve())]
    def denied(path):
        raise OSError("blocked")
    monkeypatch.setattr(os, "startfile", denied)
    monkeypatch.setattr(result_ui.QMessageBox, "warning", lambda *args: warnings.append(args))
    assert not open_result_folder(None, tmp_path)
    assert "blocked" in warnings[0][-1]
