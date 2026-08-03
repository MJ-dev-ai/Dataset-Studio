from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.mapset import MapSet, discover_map_sets
from config.default_presets import IMAGE_EXTENSIONS, MAP_SPECS

PROJECT_MANIFEST = ".datasetstudio.json"

@dataclass
class DatasetProject:
    """Runtime project state for a folder-backed Dataset Editor workspace."""

    root_path: Path
    mapsets: list[MapSet]
    current_image_path: Path | None = None

    @property
    def name(self) -> str:
        return self.root_path.name or str(self.root_path)

def open_dataset_project(root_path: str | Path) -> DatasetProject:
    """Scan a dataset folder and return a project state object."""
    root = Path(root_path).resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Dataset folder does not exist: {root}")
    mapsets = discover_map_sets(root, MAP_SPECS, IMAGE_EXTENSIONS)
    return DatasetProject(root_path=root, mapsets=mapsets)
