from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

ROI_CONTOUR_KEY = "__mapset_roi__"

@dataclass(frozen=True)
class MapSet:
	"""A folder-backed sample whose images share one coordinate system and label file."""

	folder: Path
	maps: tuple[tuple[str, Path], ...]
	label_path: Path | None
	roi_contours: tuple[tuple[str, tuple[tuple[tuple[float, float], ...], ...]], ...] = field(default_factory=tuple)

	@property
	def name(self) -> str:
		if self.folder.is_file():
			return self.folder.stem
		return self.folder.name or str(self.folder)

	@property
	def map_paths(self) -> dict[str, Path]:
		return dict(self.maps)

	@property
	def reference_path(self) -> Path:
		paths = self.map_paths
		return paths.get("albedo_map", paths.get("image", self.maps[0][1]))

	@property
	def roi_contour_map(self) -> dict[str, tuple[tuple[tuple[float, float], ...], ...]]:
		return dict(self.roi_contours)

	@property
	def roi_contour(self) -> tuple[tuple[tuple[float, float], ...], ...]:
		"""Return the MapSet-level ROI contour used by AutoAugment."""
		return self.roi_contour_map.get(ROI_CONTOUR_KEY, tuple())

def discover_map_sets(
	root: str | os.PathLike,
	map_specs: Iterable[tuple[str, str]],
	image_extensions: Iterable[str],
	cancelled: Callable[[], bool] | None = None,
	progress: Callable[[int, str], None] | None = None,
) -> list[MapSet]:
	"""Discover first-level folder MapSets and root-level single-image MapSets."""
	root_path = Path(root).resolve()
	extensions = {extension.casefold() for extension in image_extensions}
	configured = {filename.casefold(): key for filename, key in map_specs}
	order = {key: index for index, (_filename, key) in enumerate(map_specs)}
	discovered: list[MapSet] = []
	scanned = 0

	for child in sorted(root_path.iterdir(), key=lambda item: item.name.casefold()):
		if cancelled is not None and cancelled():
			break
		if _is_preview_name(child.name):
			continue

		if child.is_dir():
			images = _image_files_in_folder(child, extensions)
			if not images:
				continue
			discovered.append(_folder_mapset(child, images, configured, order))
			scanned += 1
			if progress is not None:
				progress(scanned, str(child))
			continue

		if child.is_file() and _is_image_file(child, extensions):
			discovered.append(_single_image_mapset(child))
			scanned += 1
			if progress is not None:
				progress(scanned, str(child))

	return sorted(discovered, key=lambda item: str(item.folder).casefold())

def mapset_from_image_path(image_path: str | os.PathLike) -> MapSet:
	"""Create a single-image MapSet from an explicitly selected image."""
	path = Path(image_path).resolve()
	label_candidate = path.with_suffix(".txt")
	return MapSet(
		folder=path,
		maps=(("image", path),),
		label_path=label_candidate if label_candidate.is_file() else None,
	)

def _folder_mapset(
	folder: Path,
	images: list[Path],
	configured: dict[str, str],
	order: dict[str, int],
) -> MapSet:
	known = []
	extras = []
	used_keys = set()
	for path in images:
		key = configured.get(path.name.casefold(), path.stem)
		candidate = key
		serial = 2
		while candidate.casefold() in used_keys:
			candidate = f"{key}_{serial}"
			serial += 1
		used_keys.add(candidate.casefold())
		pair = (candidate, path.resolve())
		if path.name.casefold() in configured:
			known.append(pair)
		else:
			extras.append(pair)

	known.sort(key=lambda item: order.get(item[0], len(order)))
	extras.sort(key=lambda item: item[0].casefold())
	label_candidate = folder / f"{folder.name}.txt"
	return MapSet(
		folder=folder.resolve(),
		maps=tuple([*known, *extras]),
		label_path=label_candidate.resolve() if label_candidate.is_file() else None,
	)

def _single_image_mapset(image_path: Path) -> MapSet:
	return mapset_from_image_path(image_path)

def _image_files_in_folder(folder: Path, extensions: set[str]) -> list[Path]:
	try:
		items = list(folder.iterdir())
	except OSError:
		return []
	return [
		item
		for item in sorted(items, key=lambda path: path.name.casefold())
		if item.is_file() and _is_image_file(item, extensions)
	]

def _is_image_file(path: Path, extensions: set[str]) -> bool:
	return (
		path.suffix.casefold() in extensions
		and not _is_preview_name(path.name)
		and not _is_auxiliary_map_file(path.name)
	)

def _is_preview_name(name: str) -> bool:
	return "_preview" in name.casefold()

def _is_auxiliary_map_file(name: str) -> bool:
	stem = Path(name).stem.casefold()
	return stem.endswith("_placement_mask") or stem.endswith("_placement_contour")
