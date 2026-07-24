from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import uuid

import numpy as np

from core.image_io import read_image


PATCH_MIME_TYPE = "application/x-datasetstudio-patch-id"


def read_defect_pool(root: Path) -> list[dict]:
    """Read exported ``class/id_map.png`` defects as aligned clipboard payloads."""
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f"Defect Pool folder does not exist: {root}")
    payloads: list[dict] = []
    for class_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        grouped: dict[str, dict[str, Path]] = {}
        for path in sorted(class_dir.glob("*.png")):
            if path.stem.endswith("_mask") or "_" not in path.stem:
                continue
            defect_id, map_key = path.stem.split("_", 1)
            grouped.setdefault(defect_id, {})[map_key] = path
        for defect_id, map_paths in sorted(grouped.items()):
            maps: dict[str, np.ndarray] = {}
            masks: list[np.ndarray] = []
            for map_key, image_path in map_paths.items():
                image = read_image(image_path)
                mask_path = image_path.with_name(f"{image_path.stem}_mask.png")
                mask_image = read_image(mask_path) if mask_path.exists() else None
                if image is None or image.size == 0 or mask_image is None or mask_image.size == 0:
                    continue
                mask = np.max(mask_image[:, :, :3], axis=2) if mask_image.ndim == 3 else mask_image
                maps[map_key] = image
                masks.append(mask > 0)
            if not maps or not masks:
                continue
            shape = next(iter(maps.values())).shape[:2]
            if any(image.shape[:2] != shape for image in maps.values()) or any(mask.shape != shape for mask in masks):
                continue
            payloads.append({
                "name": f"{class_dir.name} {defect_id}",
                "maps": maps,
                "mask": np.where(np.logical_or.reduce(masks), 255, 0).astype(np.uint8),
                "source_path": class_dir,
                "preview_key": "albedo_map" if "albedo_map" in maps else next(iter(maps)),
            })
    return payloads


@dataclass(frozen=True)
class PatchClip:
    """Aligned per-map patch images stored as one MapSet clipboard item."""

    clip_id: str
    name: str
    maps: tuple[tuple[str, np.ndarray], ...]
    mask: np.ndarray
    source_path: Path | None = None
    preview_key: str = ""

    @property
    def map_images(self) -> dict[str, np.ndarray]:
        return dict(self.maps)

    @property
    def map_keys(self) -> tuple[str, ...]:
        return tuple(key for key, _image in self.maps)

    @property
    def image(self) -> np.ndarray:
        """Return the preferred thumbnail/preview image."""
        images = self.map_images
        if self.preview_key in images:
            return images[self.preview_key]
        return self.maps[0][1]

    def image_for(self, map_key: str) -> np.ndarray:
        """Return the source patch corresponding to one target map key."""
        try:
            return self.map_images[str(map_key)]
        except KeyError as exc:
            raise KeyError(f"Clipboard patch has no map key: {map_key}") from exc


class PatchClipboard:
    """Own multiple stable-ID patch clips independently from active placement."""

    def __init__(self) -> None:
        self._clips: dict[str, PatchClip] = {}
        self._sequence = 0

    def __len__(self) -> int:
        return len(self._clips)

    def items(self) -> tuple[PatchClip, ...]:
        """Return clips in insertion order."""
        return tuple(self._clips.values())

    def get(self, clip_id: str) -> PatchClip | None:
        """Return one clip without transferring ownership."""
        return self._clips.get(str(clip_id))

    def add(
        self,
        image: np.ndarray,
        mask: np.ndarray,
        name: str,
        source_path: Path | None = None,
    ) -> PatchClip:
        """Store a backward-compatible single-image patch clip."""
        return self.add_mapset(
            {"image": image},
            mask,
            name,
            source_path,
            preview_key="image",
        )

    def add_mapset(
        self,
        map_images: dict[str, np.ndarray],
        mask: np.ndarray,
        name: str,
        source_path: Path | None = None,
        *,
        preview_key: str = "",
    ) -> PatchClip:
        """Validate and store owned aligned patches for every source MapSet map."""
        if not map_images:
            raise ValueError("MapSet patch contains no map images")
        if mask is None or mask.size == 0:
            raise ValueError("patch mask is empty")
        owned_maps: list[tuple[str, np.ndarray]] = []
        expected_shape = mask.shape[:2]
        for map_key, image in map_images.items():
            if image is None or image.size == 0:
                raise ValueError(f"patch image is empty: {map_key}")
            if image.shape[:2] != expected_shape:
                raise ValueError(f"MapSet patch size mismatch: {map_key}")
            owned_maps.append((str(map_key), np.ascontiguousarray(image.copy())))
        self._sequence += 1
        normalized_name = str(name).strip() or f"Patch {self._sequence}"
        clip = PatchClip(
            clip_id=uuid.uuid4().hex,
            name=normalized_name,
            maps=tuple(owned_maps),
            mask=np.ascontiguousarray(np.where(mask > 0, 255, 0).astype(np.uint8)),
            source_path=Path(source_path).resolve() if source_path is not None else None,
            preview_key=str(preview_key),
        )
        self._clips[clip.clip_id] = clip
        return clip

    def remove(self, clip_id: str) -> bool:
        """Remove one clip while preserving every other stable ID."""
        return self._clips.pop(str(clip_id), None) is not None

    def clear(self) -> None:
        """Remove every stored clip."""
        self._clips.clear()
