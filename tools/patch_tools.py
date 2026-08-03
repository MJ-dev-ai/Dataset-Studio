from __future__ import annotations

from dataclasses import dataclass
import math

import cv2
import numpy as np

from core.image_ops import rotate_bound
from core.mask_ops import make_nonzero_mask
from core.patch_clipboard import PatchClip


def transform_patch(
    image: np.ndarray,
    scale: float,
    angle: float,
    mask: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Scale and rotate a patch while preserving its binary selection mask."""
    height, width = image.shape[:2]
    size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    scaled = cv2.resize(image, size, interpolation=cv2.INTER_LINEAR)
    scaled_mask = (
        make_nonzero_mask(scaled)
        if mask is None
        else cv2.resize(mask, size, interpolation=cv2.INTER_NEAREST)
    )
    rotated = rotate_bound(scaled, angle, interpolation=cv2.INTER_LINEAR)
    rotated_mask = rotate_bound(scaled_mask, angle, interpolation=cv2.INTER_NEAREST)
    if rotated_mask.ndim == 3:
        rotated_mask = np.max(rotated_mask[:, :, :3], axis=2)
    return rotated, np.where(rotated_mask > 0, 255, 0).astype(np.uint8)


@dataclass
class PatchState:
    patch: np.ndarray | None = None
    mask: np.ndarray | None = None
    x_pos: int = 0
    y_pos: int = 0
    scale: float = 1.0
    angle: float = 0.0
    source_name: str = ""
    clip_id: str = ""
    map_key: str = ""
    placement_active: bool = False


@dataclass
class PatchPreview:
    patch: np.ndarray
    mask: np.ndarray
    x_pos: int
    y_pos: int


class PatchTool:
    """Calculate transformed patch placement state."""

    def __init__(self):
        self.state = PatchState()
        self._move_drag_active = False
        self._move_pointer_start = None
        self._move_position_start: tuple[int, int] = (0, 0)
        self._rotation_drag_active = False
        self._rotation_pointer_start = 0.0
        self._rotation_angle_start = 0.0
        self._active_clip: PatchClip | None = None
        self._target_size: tuple[int, int] | None = None

    @property
    def has_active_placement(self) -> bool:
        return self.state.placement_active and self.state.patch is not None

    @property
    def is_moving_patch(self) -> bool:
        return self._move_drag_active

    @property
    def is_rotating_patch(self) -> bool:
        return self._rotation_drag_active

    def set_target_size(self, width: int, height: int) -> None:
        if width <= 0 or height <= 0:
            self._target_size = None
            return
        self._target_size = (int(width), int(height))
        self._normalize_position()

    def begin_move_drag(self, image_position) -> bool:
        if not self.has_active_placement:
            return False
        self._move_drag_active = True
        self._move_pointer_start = image_position
        self._move_position_start = (self.state.x_pos, self.state.y_pos)
        return True

    def update_move_drag(self, image_position) -> bool:
        if not self.has_active_placement or not self._move_drag_active:
            return False
        if self._move_pointer_start is None:
            self._move_pointer_start = image_position
            self._move_position_start = (self.state.x_pos, self.state.y_pos)
        dx = image_position.x() - self._move_pointer_start.x()
        dy = image_position.y() - self._move_pointer_start.y()
        return self.set_position(
            round(self._move_position_start[0] + dx),
            round(self._move_position_start[1] + dy),
        )

    def end_move_drag(self) -> None:
        self._move_drag_active = False
        self._move_pointer_start = None

    def begin_rotation_drag(self, image_position) -> bool:
        if not self.has_active_placement:
            return False
        self._rotation_drag_active = True
        self._rotation_pointer_start = self._pointer_angle(image_position)
        self._rotation_angle_start = self.state.angle
        return True

    def update_rotation_drag(self, image_position) -> bool:
        if not self.has_active_placement or not self._rotation_drag_active:
            return False
        delta = math.degrees(self._pointer_angle(image_position) - self._rotation_pointer_start)
        return self.set_rotation(self._rotation_angle_start + delta)

    def end_rotation_drag(self) -> None:
        self._rotation_drag_active = False

    def load_selection_patch(
        self,
        patch: np.ndarray,
        mask: np.ndarray,
        x_pos: int,
        y_pos: int,
        source_name: str = "",
    ) -> bool:
        """Store a copied patch without starting placement."""
        if patch is None or patch.size == 0 or mask is None or mask.size == 0:
            return False
        if not np.any(mask):
            return False
        self._active_clip = None
        self.state = PatchState(
            patch=patch.copy(),
            mask=mask.copy(),
            x_pos=int(x_pos),
            y_pos=int(y_pos),
            scale=1.0,
            angle=0.0,
            source_name=str(source_name),
            clip_id="",
            map_key="",
            placement_active=False,
        )
        return True

    def paste_preview(self) -> bool:
        return self.state.placement_active and self.state.patch is not None

    def load_clip(
        self,
        clip: PatchClip,
        center_x: float,
        center_y: float,
        map_key: str,
        target_size: tuple[int, int],
    ) -> bool:
        """Load one clipboard clip and begin placement at a target-image position."""
        try:
            preview_image = clip.image_for(map_key)
        except KeyError:
            return False
        self._active_clip = clip
        self.set_target_size(*target_size)
        self.state = PatchState(
            patch=preview_image.copy(),
            mask=clip.mask.copy(),
            scale=1.0,
            angle=0.0,
            source_name=clip.name,
            clip_id=clip.clip_id,
            map_key=str(map_key),
            placement_active=True,
        )
        self.state.x_pos = round(float(center_x) - preview_image.shape[1] / 2.0)
        self.state.y_pos = round(float(center_y) - preview_image.shape[0] / 2.0)
        self._normalize_position()
        return True

    def set_active_map_key(self, map_key: str, target_size: tuple[int, int]) -> bool:
        """Switch preview pixels while preserving the MapSet placement transform."""
        if self._active_clip is None or not self.state.placement_active:
            return False
        try:
            image = self._active_clip.image_for(map_key)
        except KeyError:
            return False
        self.set_target_size(*target_size)
        center = self._patch_center()
        self.state.patch = image.copy()
        self.state.map_key = str(map_key)
        self._restore_patch_center(center)
        return True

    def begin_placement(
        self,
        target_size: tuple[int, int],
        x_pos: int | None = None,
        y_pos: int | None = None,
    ) -> bool:
        """Activate placement for a loaded patch without changing clipboard ownership."""
        if self.state.patch is None or self.state.mask is None:
            return False
        self.set_target_size(*target_size)
        if self._target_size is None:
            return False
        self.state.placement_active = True
        if x_pos is not None:
            self.state.x_pos = int(x_pos)
        if y_pos is not None:
            self.state.y_pos = int(y_pos)
        self._normalize_position()
        return True

    def clear_active_patch(self) -> None:
        """End placement and discard only the tool copy, not the clipboard model clip."""
        self._move_drag_active = False
        self._move_pointer_start = None
        self._rotation_drag_active = False
        self._active_clip = None
        self.state = PatchState()

    def transformed_patch(self) -> tuple[np.ndarray, np.ndarray]:
        """Return the patch and mask after the current scale and rotation."""
        if self.state.patch is None or self.state.mask is None:
            raise ValueError("Copy a selection before transforming a patch")
        return transform_patch(
            self.state.patch,
            self.state.scale,
            self.state.angle,
            self.state.mask,
        )

    def preview_payload(self) -> PatchPreview | None:
        if not self.state.placement_active or self.state.patch is None or self.state.mask is None:
            return None
        target_size = self._target_size
        if target_size is None:
            return None
        patch, mask = self.transformed_patch()
        if patch.shape[1] > target_size[0] or patch.shape[0] > target_size[1]:
            return None
        x_pos, y_pos = self._clamped_position(patch.shape[1], patch.shape[0])
        self.state.x_pos, self.state.y_pos = x_pos, y_pos
        return PatchPreview(patch=patch, mask=mask, x_pos=x_pos, y_pos=y_pos)

    def composition_inputs(
        self,
        target: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, int, int]:
        """Create owned arrays and a placement safe for background composition."""
        if not self.state.placement_active:
            raise ValueError("Drag a clipboard patch onto the target image first")
        if target is None or target.size == 0:
            raise ValueError("Target image is empty")
        patch, mask = self.transformed_patch()
        if patch.shape[1] > target.shape[1] or patch.shape[0] > target.shape[0]:
            raise ValueError("Transformed patch is larger than the target image")
        x_pos, y_pos = self._clamped_position(patch.shape[1], patch.shape[0], (target.shape[1], target.shape[0]))
        return target.copy(), patch.copy(), mask.copy(), x_pos, y_pos

    def mapset_composition_inputs(
        self,
        target_images: dict[str, np.ndarray],
    ) -> dict[str, tuple[np.ndarray, np.ndarray, np.ndarray, int, int]]:
        """Build aligned transformed inputs for every corresponding target map."""
        if not self.state.placement_active or self._active_clip is None:
            raise ValueError("Drag a MapSet patch onto the target first")
        source_maps = self._active_clip.map_images
        target_keys = tuple(target_images)
        missing = [key for key in target_keys if key not in source_maps]
        if missing:
            raise ValueError(f"Clipboard patch is missing target map keys: {missing}")

        result: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray, int, int]] = {}
        expected_shape: tuple[int, int] | None = None
        for map_key in target_keys:
            target = target_images[map_key]
            if target is None or target.size == 0:
                raise ValueError(f"Target map is empty: {map_key}")
            if expected_shape is None:
                expected_shape = target.shape[:2]
            elif target.shape[:2] != expected_shape:
                raise ValueError("Target MapSet maps do not share one coordinate system")
            patch, mask = transform_patch(
                source_maps[map_key],
                self.state.scale,
                self.state.angle,
                self._active_clip.mask,
            )
            if patch.shape[1] > target.shape[1] or patch.shape[0] > target.shape[0]:
                raise ValueError(f"Transformed patch is larger than target map: {map_key}")
            x_pos = max(0, min(self.state.x_pos, target.shape[1] - patch.shape[1]))
            y_pos = max(0, min(self.state.y_pos, target.shape[0] - patch.shape[0]))
            result[map_key] = (
                target.copy(),
                patch.copy(),
                mask.copy(),
                int(x_pos),
                int(y_pos),
            )
        return result

    def rotate(self, degrees: float) -> bool:
        return self.set_rotation(self.state.angle + degrees)

    def scale(self, factor: float) -> bool:
        return self.set_scale(self.state.scale * factor)

    def reset_transform(self) -> bool:
        if self.state.patch is None:
            return False
        center = self._patch_center()
        self.state.scale, self.state.angle = 1.0, 0.0
        self._restore_patch_center(center)
        return True

    def set_position(self, x_pos: int, y_pos: int) -> bool:
        """Set patch top-left coordinates."""
        if self.state.patch is None:
            return False
        self.state.x_pos = int(x_pos)
        self.state.y_pos = int(y_pos)
        self._normalize_position()
        return True

    def set_rotation(self, degrees: float) -> bool:
        """Set an absolute patch rotation in degrees."""
        if self.state.patch is None:
            return False
        center = self._patch_center()
        self.state.angle = float(degrees) % 360
        self._restore_patch_center(center)
        return True

    def set_scale(self, scale: float) -> bool:
        """Set an absolute patch scale within the supported range."""
        if self.state.patch is None:
            return False
        center = self._patch_center()
        self.state.scale = max(0.1, min(10.0, float(scale)))
        self._restore_patch_center(center)
        return True

    def _patch_center(self) -> tuple[float, float]:
        patch, _ = self.transformed_patch()
        return (
            self.state.x_pos + patch.shape[1] / 2.0,
            self.state.y_pos + patch.shape[0] / 2.0,
        )

    def _restore_patch_center(self, center: tuple[float, float]) -> None:
        patch, _ = self.transformed_patch()
        self.state.x_pos = round(center[0] - patch.shape[1] / 2.0)
        self.state.y_pos = round(center[1] - patch.shape[0] / 2.0)
        self._normalize_position()

    def _normalize_position(self) -> None:
        target_size = self._target_size
        if target_size is None:
            return
        try:
            patch, _ = self.transformed_patch()
        except ValueError:
            return
        if patch.shape[1] > target_size[0] or patch.shape[0] > target_size[1]:
            return
        self.state.x_pos, self.state.y_pos = self._clamped_position(
            patch.shape[1],
            patch.shape[0],
            target_size,
        )

    def _clamped_position(
        self,
        patch_width: int,
        patch_height: int,
        target_size: tuple[int, int] | None = None,
    ) -> tuple[int, int]:
        width, height = target_size or self._target_size or (patch_width, patch_height)
        return (
            max(0, min(int(self.state.x_pos), width - patch_width)),
            max(0, min(int(self.state.y_pos), height - patch_height)),
        )

    def _pointer_angle(self, image_position) -> float:
        patch, _ = self.transformed_patch()
        center_x = self.state.x_pos + patch.shape[1] / 2.0
        center_y = self.state.y_pos + patch.shape[0] / 2.0
        return math.atan2(image_position.y() - center_y, image_position.x() - center_x)
