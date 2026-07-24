from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
import math

import cv2
import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage

from core.qt_image import bgr_mask_to_qpixmap, qimage_to_bgr
from core.patch_clipboard import PatchClip
from service.editing_service import transform_patch


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


class PatchTool:
    """Copy a selection and apply a transformed Poisson patch."""

    def __init__(self, canvas):
        self.canvas = canvas
        self.state = PatchState()
        self.state_changed: Callable[[PatchState], None] | None = None
        self._move_drag_active = False
        self._move_pointer_start = None
        self._move_position_start: tuple[int, int] = (0, 0)
        self._rotation_drag_active = False
        self._rotation_pointer_start = 0.0
        self._rotation_angle_start = 0.0
        self._active_clip: PatchClip | None = None
        self.canvas.image_changed.connect(self._on_canvas_image_changed)

    def activate(self) -> None:
        self.canvas.setCursor(Qt.CursorShape.SizeAllCursor)
        self._refresh_preview()

    def deactivate(self) -> None:
        self._move_drag_active = False
        self._move_pointer_start = None
        self._rotation_drag_active = False
        self.canvas.unsetCursor()
        self.canvas.clear_patch_preview()

    def mouse_press_event(self, event) -> None:
        if not self.state.placement_active or self.state.patch is None:
            return
        pos = self.canvas.to_image_pos(event.position())
        if event.button() == Qt.MouseButton.RightButton:
            self._rotation_drag_active = True
            self._rotation_pointer_start = self._pointer_angle(pos)
            self._rotation_angle_start = self.state.angle
            event.accept()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._move_drag_active = True
        self._move_pointer_start = pos
        self._move_position_start = (self.state.x_pos, self.state.y_pos)
        event.accept()

    def mouse_move_event(self, event) -> None:
        if not self.state.placement_active or self.state.patch is None:
            return
        if self._rotation_drag_active and event.buttons() & Qt.MouseButton.RightButton:
            pos = self.canvas.to_image_pos(event.position())
            delta = math.degrees(self._pointer_angle(pos) - self._rotation_pointer_start)
            self.set_rotation(self._rotation_angle_start + delta)
            event.accept()
            return
        if self._move_drag_active and event.buttons() & Qt.MouseButton.LeftButton:
            pos = self.canvas.to_image_pos(event.position())
            if self._move_pointer_start is None:
                self._move_pointer_start = pos
                self._move_position_start = (self.state.x_pos, self.state.y_pos)
            dx = pos.x() - self._move_pointer_start.x()
            dy = pos.y() - self._move_pointer_start.y()
            self.set_position(
                round(self._move_position_start[0] + dx),
                round(self._move_position_start[1] + dy),
            )
            event.accept()

    def mouse_release_event(self, event) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self._rotation_drag_active = False
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._move_drag_active = False
            self._move_pointer_start = None
            event.accept()

    def copy_from_selection(self, source_name: str = "") -> bool:
        """Copy the active selection and preserve its exact rasterized mask."""
        if self.canvas.pixmap.isNull() or not self.canvas.has_selection():
            return False
        bounds = self.canvas.selection_bounds().toAlignedRect().intersected(self.canvas.pixmap.rect())
        if bounds.isEmpty():
            return False
        source = qimage_to_bgr(self.canvas.pixmap)
        self.state.patch = source[bounds.top():bounds.bottom() + 1, bounds.left():bounds.right() + 1].copy()
        self.state.mask = self._selection_mask_array(bounds)
        if self.state.mask is None or not np.any(self.state.mask):
            return False
        self.state.x_pos, self.state.y_pos = bounds.x(), bounds.y()
        self.state.scale, self.state.angle = 1.0, 0.0
        self.state.source_name = str(source_name)
        self.state.clip_id = ""
        self.state.placement_active = False
        self._notify_state_changed()
        return True

    def paste_preview(self) -> bool:
        return self.state.placement_active and self.state.patch is not None

    def load_clip(
        self,
        clip: PatchClip,
        center_x: float,
        center_y: float,
        map_key: str,
    ) -> bool:
        """Load one clipboard clip and begin placement at a canvas drop position."""
        try:
            preview_image = clip.image_for(map_key)
        except KeyError:
            return False
        self._active_clip = clip
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
        self._notify_state_changed()
        return True

    def set_active_map_key(self, map_key: str) -> bool:
        """Switch preview pixels while preserving the MapSet placement transform."""
        if self._active_clip is None or not self.state.placement_active:
            return False
        try:
            image = self._active_clip.image_for(map_key)
        except KeyError:
            self.canvas.clear_patch_preview()
            return False
        center = self._patch_center()
        self.state.patch = image.copy()
        self.state.map_key = str(map_key)
        self._restore_patch_center(center)
        self._notify_state_changed()
        return True

    def begin_placement(self, x_pos: int | None = None, y_pos: int | None = None) -> bool:
        """Activate placement for a loaded patch without changing clipboard ownership."""
        if self.state.patch is None or self.state.mask is None or self.canvas.pixmap.isNull():
            return False
        self.state.placement_active = True
        if x_pos is not None:
            self.state.x_pos = int(x_pos)
        if y_pos is not None:
            self.state.y_pos = int(y_pos)
        self._normalize_position()
        self._notify_state_changed()
        return True

    def clear_active_patch(self) -> None:
        """End placement and discard only the tool copy, not the clipboard model clip."""
        self._move_drag_active = False
        self._move_pointer_start = None
        self._rotation_drag_active = False
        self._active_clip = None
        self.state = PatchState()
        self.canvas.clear_patch_preview()
        if self.state_changed is not None:
            self.state_changed(self.state)

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

    def composition_inputs(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, int, int]:
        """Create owned arrays and a placement safe for background composition."""
        if not self.state.placement_active:
            raise ValueError("Drag a clipboard patch onto the target image first")
        if self.canvas.pixmap.isNull():
            raise ValueError("Target image is empty")
        patch, mask = self.transformed_patch()
        target = qimage_to_bgr(self.canvas.pixmap)
        if patch.shape[1] > target.shape[1] or patch.shape[0] > target.shape[0]:
            raise ValueError("Transformed patch is larger than the target image")
        x_pos, y_pos = self._clamped_position(patch.shape[1], patch.shape[0])
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

    def _selection_mask_array(self, bounds) -> np.ndarray | None:
        mask_image = self.canvas.selection_mask(bounds)
        if mask_image.isNull():
            return None
        gray = mask_image.convertToFormat(QImage.Format.Format_Grayscale8)
        bits = gray.bits()
        bits.setsize(gray.sizeInBytes())
        view = np.frombuffer(bits, dtype=np.uint8).reshape(gray.height(), gray.bytesPerLine())
        return np.where(view[:, :gray.width()] > 0, 255, 0).astype(np.uint8).copy()

    def rotate(self, degrees: float) -> bool:
        return self.set_rotation(self.state.angle + degrees)

    def scale(self, factor: float) -> bool:
        return self.set_scale(self.state.scale * factor)

    def reset_transform(self) -> None:
        if self.state.patch is None:
            return
        center = self._patch_center()
        self.state.scale, self.state.angle = 1.0, 0.0
        self._restore_patch_center(center)
        self._notify_state_changed()

    def set_position(self, x_pos: int, y_pos: int) -> bool:
        """Set patch top-left coordinates and refresh the non-destructive preview."""
        if self.state.patch is None:
            return False
        self.state.x_pos = int(x_pos)
        self.state.y_pos = int(y_pos)
        self._normalize_position()
        self._notify_state_changed()
        return True

    def set_rotation(self, degrees: float) -> bool:
        """Set an absolute patch rotation in degrees."""
        if self.state.patch is None:
            return False
        center = self._patch_center()
        self.state.angle = float(degrees) % 360
        self._restore_patch_center(center)
        self._notify_state_changed()
        return True

    def set_scale(self, scale: float) -> bool:
        """Set an absolute patch scale within the supported range."""
        if self.state.patch is None:
            return False
        center = self._patch_center()
        self.state.scale = max(0.1, min(10.0, float(scale)))
        self._restore_patch_center(center)
        self._notify_state_changed()
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
        if self.canvas.pixmap.isNull():
            return
        try:
            patch, _ = self.transformed_patch()
        except ValueError:
            return
        if patch.shape[1] > self.canvas.pixmap.width() or patch.shape[0] > self.canvas.pixmap.height():
            return
        self.state.x_pos, self.state.y_pos = self._clamped_position(
            patch.shape[1], patch.shape[0]
        )

    def _clamped_position(self, patch_width: int, patch_height: int) -> tuple[int, int]:
        width = self.canvas.pixmap.width()
        height = self.canvas.pixmap.height()
        return (
            max(0, min(int(self.state.x_pos), width - patch_width)),
            max(0, min(int(self.state.y_pos), height - patch_height)),
        )

    def _pointer_angle(self, image_position) -> float:
        patch, _ = self.transformed_patch()
        center_x = self.state.x_pos + patch.shape[1] / 2.0
        center_y = self.state.y_pos + patch.shape[0] / 2.0
        return math.atan2(image_position.y() - center_y, image_position.x() - center_x)

    def _refresh_preview(self) -> None:
        if (
            not self.state.placement_active
            or self.state.patch is None
            or self.state.mask is None
            or self.canvas.pixmap.isNull()
        ):
            self.canvas.clear_patch_preview()
            return
        try:
            patch, mask = self.transformed_patch()
            if patch.shape[1] > self.canvas.pixmap.width() or patch.shape[0] > self.canvas.pixmap.height():
                self.canvas.clear_patch_preview()
                return
            x_pos, y_pos = self._clamped_position(patch.shape[1], patch.shape[0])
            self.canvas.set_patch_preview(bgr_mask_to_qpixmap(patch, mask), x_pos, y_pos)
        except (ValueError, cv2.error):
            self.canvas.clear_patch_preview()

    def _notify_state_changed(self) -> None:
        self._refresh_preview()
        if self.state_changed is not None:
            self.state_changed(self.state)

    def _on_canvas_image_changed(self) -> None:
        self._refresh_preview()
        if self.state_changed is not None:
            self.state_changed(self.state)
