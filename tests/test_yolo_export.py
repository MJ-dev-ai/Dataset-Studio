from pathlib import Path

from service.yolo_export_service import YoloExportApi, YoloExportOptions
from core.mapset import MapSet


def test_validate_export_rejects_missing_label_pair(tmp_path):
    root = tmp_path / "albedo_map"
    (root / "images" / "train").mkdir(parents=True)
    (root / "labels" / "train").mkdir(parents=True)
    (root / "images" / "train" / "sample.png").touch()
    (root / "data.yaml").write_text("names: []\n", encoding="utf-8")
    assert not YoloExportApi().validate_export(tmp_path)


def test_split_is_deterministic():
    options = YoloExportOptions(Path("out"), ["class0"], seed=7)
    items = list(range(10))
    api = YoloExportApi()
    assert api.split_train_val_test(items, options) == api.split_train_val_test(items, options)


def test_export_creates_empty_txt_for_mapset_without_labels(tmp_path):
    """Negative images must retain an empty YOLO label pair during export."""
    source = tmp_path / "source"
    source.mkdir()
    image = source / "albedo_map.png"
    image.write_bytes(b"image")
    mapset = MapSet(
        folder=source,
        maps=(("albedo_map", image),),
        label_path=None,
    )
    output = tmp_path / "export"
    options = YoloExportOptions(
        output_root=output,
        class_names=["Scratch"],
        train_ratio=1.0,
        val_ratio=0.0,
        test_ratio=0.0,
    )

    result = YoloExportApi().export_dataset([mapset], options)

    label = output / "albedo_map" / "labels" / "train" / "source.txt"
    assert label.is_file()
    assert label.read_bytes() == b""
    assert result == {"images": 1, "labels": 1}


def test_export_keeps_empty_existing_label_file(tmp_path):
    """An existing zero-line label file is also a valid negative sample."""
    source = tmp_path / "negative"
    source.mkdir()
    image = source / "normal_map.png"
    image.write_bytes(b"image")
    label_source = source / "negative.txt"
    label_source.write_text("", encoding="utf-8")
    mapset = MapSet(source, (("normal_map", image),), label_source)
    output = tmp_path / "export"
    options = YoloExportOptions(output, ["Scratch"], 1.0, 0.0, 0.0)

    YoloExportApi().export_dataset([mapset], options)

    assert (output / "normal_map" / "labels" / "train" / "negative.txt").read_bytes() == b""
