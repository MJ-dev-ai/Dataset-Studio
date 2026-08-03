from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.mapset import MapSet

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
