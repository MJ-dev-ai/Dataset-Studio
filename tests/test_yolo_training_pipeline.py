from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from config.yolo_train_config import build_config
from utils.yolo_dataset_tools import (
	YoloItem,
	build_train_kwargs,
	load_class_names,
	resolve_dataset_yaml_paths,
	split_yolo_items,
	validate_resume_checkpoint,
	write_data_yaml,
)


def _make_dataset(tmp_path: Path) -> Path:
	"""Create the smallest valid train/val/test YOLO dataset."""
	root = tmp_path / "dataset"
	for split in ("train", "val", "test"):
		(root / "images" / split).mkdir(parents=True)
		(root / "labels" / split).mkdir(parents=True)
		(root / "images" / split / f"{split}.png").touch()
		(root / "labels" / split / f"{split}.txt").write_text(
			"0 0.5 0.5 0.2 0.2\n", encoding="utf-8"
		)
	(root / "data.yaml").write_text(
		yaml.safe_dump(
			{
				"path": str(root),
				"train": "images/train",
				"val": "images/val",
				"test": "images/test",
				"names": {0: "Scratch"},
			},
			sort_keys=False,
		),
		encoding="utf-8",
	)
	return root


def test_build_config_honors_augmentation_override(tmp_path: Path) -> None:
	"""A user override must control both config and train arguments."""
	root = _make_dataset(tmp_path)
	config = build_config(
		{
			"dataset_root": root,
			"workspace_root": tmp_path,
			"output_root": tmp_path / "runs",
			"augmentation": False,
			"device": "cpu",
		},
		validate=True,
	)

	assert config["augmentation"]["enabled"] is False
	assert config["new_train"]["augmentation"] is False


def test_build_train_kwargs_always_pins_custom_dataset(tmp_path: Path) -> None:
	"""Training must never silently fall back to Ultralytics' coco8.yaml."""
	root = _make_dataset(tmp_path)
	config = build_config(
		{
			"dataset_root": root,
			"workspace_root": tmp_path,
			"output_root": tmp_path / "runs",
			"device": "cpu",
		},
		validate=True,
	)

	kwargs = build_train_kwargs(config, root / "data.yaml")

	assert kwargs["data"] == str((root / "data.yaml").resolve())
	assert kwargs["project"] == str((tmp_path / "runs").resolve())
	assert kwargs["name"] == config["new_train"]["run_name"]
	assert kwargs["batch"] == 1
	assert kwargs["seed"] == 42


def test_disabled_augmentation_is_explicitly_zeroed(tmp_path: Path) -> None:
	"""Omitting augmentation kwargs would re-enable Ultralytics defaults."""
	root = _make_dataset(tmp_path)
	config = build_config(
		{
			"dataset_root": root,
			"workspace_root": tmp_path,
			"output_root": tmp_path / "runs",
			"augmentation": False,
			"device": "cpu",
		},
		validate=True,
	)

	kwargs = build_train_kwargs(config, root / "data.yaml")

	assert kwargs["hsv_h"] == 0.0
	assert kwargs["hsv_s"] == 0.0
	assert kwargs["hsv_v"] == 0.0
	assert kwargs["degrees"] == 0.0
	assert kwargs["translate"] == 0.0
	assert kwargs["scale"] == 0.0
	assert kwargs["fliplr"] == 0.0
	assert kwargs["mosaic"] == 0.0
	assert kwargs["auto_augment"] is None


def test_resume_rejects_checkpoint_trained_with_coco8(tmp_path: Path) -> None:
	"""Resume must fail before training if args.yaml points to another dataset."""
	root = _make_dataset(tmp_path)
	run_dir = tmp_path / "runs" / "bad_run"
	weights = run_dir / "weights"
	weights.mkdir(parents=True)
	checkpoint = weights / "last.pt"
	checkpoint.touch()
	(run_dir / "args.yaml").write_text("data: coco8.yaml\n", encoding="utf-8")

	with pytest.raises(ValueError, match="dataset mismatch"):
		validate_resume_checkpoint(checkpoint, root / "data.yaml")


def test_split_yolo_items_preserves_every_item_and_nonzero_splits(tmp_path: Path) -> None:
	"""Small flat datasets should not unexpectedly lose validation/test splits."""
	items = [
		YoloItem(tmp_path / f"{index}.png", tmp_path / f"{index}.txt", None)
		for index in range(10)
	]

	splits = split_yolo_items(items, 0.8, 0.1, 0.1, seed=7)

	assert {name: len(values) for name, values in splits.items()} == {
		"train": 8,
		"val": 1,
		"test": 1,
	}
	assert len({item.image_path for values in splits.values() for item in values}) == 10


def test_split_yolo_items_rejects_mixed_pre_split_data(tmp_path: Path) -> None:
	"""A partially split dataset is ambiguous and must not be silently reshuffled."""
	items = [
		YoloItem(tmp_path / "a.png", tmp_path / "a.txt", "train"),
		YoloItem(tmp_path / "b.png", tmp_path / "b.txt", None),
	]

	with pytest.raises(ValueError, match="mixes pre-split and unsplit"):
		split_yolo_items(items, 0.8, 0.1, 0.1, seed=7)


def test_data_yaml_paths_are_resolved_relative_to_path_field(tmp_path: Path) -> None:
	"""Relative split paths must resolve from data.yaml's path root."""
	root = _make_dataset(tmp_path)
	resolved = resolve_dataset_yaml_paths(root / "data.yaml")

	assert resolved["root"] == root.resolve()
	assert resolved["train"] == (root / "images" / "train").resolve()
	assert resolved["test"] == (root / "images" / "test").resolve()


def test_write_data_yaml_uses_portable_relative_split_paths(tmp_path: Path) -> None:
	"""Generated datasets should remain movable as a directory."""
	root = tmp_path / "tiles"
	root.mkdir()
	path = write_data_yaml(
		root,
		["Scratch"],
		root / "images" / "train",
		root / "images" / "val",
		root / "images" / "test",
	)
	data = yaml.safe_load(path.read_text(encoding="utf-8"))

	assert data["train"] == "images/train"
	assert data["val"] == "images/val"
	assert data["test"] == "images/test"


def test_load_class_names_rejects_sparse_mapping(tmp_path: Path) -> None:
	"""YOLO class IDs must be contiguous from zero."""
	data_yaml = tmp_path / "data.yaml"
	data_yaml.write_text("names:\n  0: Scratch\n  2: Dent\n", encoding="utf-8")

	with pytest.raises(ValueError, match="contiguous"):
		load_class_names(data_yaml)
