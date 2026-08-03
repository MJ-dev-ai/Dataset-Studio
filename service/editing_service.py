from __future__ import annotations

from collections.abc import Callable, Mapping

import cv2
import numpy as np

from core.geometry import HealingStroke, PaintStroke
from core.mask_ops import make_nonzero_mask


def clone_mode_from_text(value: str) -> int:
	"""Convert a user-facing clone mode label into an OpenCV clone constant."""
	normalized = str(value).strip().casefold().replace("_", " ")
	if normalized in {"normal", "normal clone"}:
		return cv2.NORMAL_CLONE
	if normalized in {"mixed", "mixed clone"}:
		return cv2.MIXED_CLONE
	raise ValueError(f"Unsupported Poisson clone mode: {value}")


def apply_paint_strokes(
	image: np.ndarray,
	strokes: list[PaintStroke],
	color: tuple[int, int, int],
	size: int,
	opacity: float = 1.0,
) -> np.ndarray:
	"""Apply stored image-coordinate brush strokes to one map image."""
	if image is None or image.size == 0:
		raise ValueError("image is empty")
	result = image.copy()
	overlay = result.copy()
	bgr = tuple(int(value) for value in color[:3])
	thickness = max(1, int(size))
	for start, end in strokes:
		cv2.line(
			overlay,
			(int(round(start[0])), int(round(start[1]))),
			(int(round(end[0])), int(round(end[1]))),
			bgr,
			thickness=thickness,
			lineType=cv2.LINE_8,
		)
	alpha = float(np.clip(opacity, 0.0, 1.0))
	if alpha >= 1.0:
		return overlay
	return cv2.addWeighted(overlay, alpha, result, 1.0 - alpha, 0.0)


def apply_healing_strokes(
	image: np.ndarray,
	strokes: list[HealingStroke],
	size: int,
	opacity: float = 1.0,
	source_image: np.ndarray | None = None,
	*,
	inplace: bool = False,
	check_cancelled: Callable[[], None] | None = None,
	poisson_api: PoissonApi | None = None,
) -> np.ndarray:
	"""Apply circular NORMAL_CLONE dabs from source centers to target centers."""
	if image is None or image.size == 0:
		raise ValueError("image is empty")
	if not strokes:
		return image if inplace else image.copy()
	result = image if inplace else image.copy()
	source_reference = image.copy() if source_image is None else source_image
	if source_reference.shape != result.shape:
		raise ValueError("source image size must match target image size")
	radius = max(1, int(round(size / 2.0)))
	step = max(1, int(round(radius * 0.6)))
	alpha_scale = float(np.clip(opacity, 0.0, 1.0))
	if alpha_scale <= 0.0:
		return result
	api = poisson_api or PoissonApi()
	last_dab: tuple[int, int, int, int] | None = None
	for source_start, source_end, target_start, target_end in strokes:
		if check_cancelled is not None:
			check_cancelled()
		distance = float(
			np.hypot(
				float(target_end[0]) - float(target_start[0]),
				float(target_end[1]) - float(target_start[1]),
			)
		)
		dab_count = max(1, int(np.ceil(distance / step))) if distance > 0.0 else 0
		for index in range(dab_count + 1):
			if check_cancelled is not None and index % 8 == 0:
				check_cancelled()
			t = index / dab_count if dab_count else 0.0
			source_center = _interpolate_point(source_start, source_end, t)
			target_center = _interpolate_point(target_start, target_end, t)
			dab = (
				int(round(source_center[0])),
				int(round(source_center[1])),
				int(round(target_center[0])),
				int(round(target_center[1])),
			)
			if dab == last_dab:
				continue
			last_dab = dab
			_apply_seamless_healing_dab(
				api,
				source_reference,
				result,
				source_center,
				target_center,
				radius,
				alpha_scale,
			)
	return result


def apply_healing_to_images(
	images: Mapping[str, np.ndarray],
	strokes: list[HealingStroke],
	size: int,
	opacity: float = 1.0,
	*,
	poisson_api: PoissonApi | None = None,
	check_cancelled: Callable[[], None] | None = None,
	progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, np.ndarray]:
	"""Apply one healing brush gesture to a keyed MapSet image collection."""
	results: dict[str, np.ndarray] = {}
	total = len(images)
	if total == 0 or not strokes:
		return results
	api = poisson_api or PoissonApi()
	for index, (key, image) in enumerate(images.items(), start=1):
		if check_cancelled is not None:
			check_cancelled()
		if image is None or image.size == 0:
			raise ValueError(f"image is empty: {key}")
		source = np.ascontiguousarray(image)
		target = source.copy()
		results[key] = apply_healing_strokes(
			target,
			strokes,
			size,
			opacity,
			source_image=source,
			inplace=True,
			check_cancelled=check_cancelled,
			poisson_api=api,
		)
		if progress is not None:
			progress(index, total, key)
	return results


def _interpolate_point(
	start: tuple[float, float],
	end: tuple[float, float],
	t: float,
) -> tuple[float, float]:
	return (
		float(start[0]) + (float(end[0]) - float(start[0])) * t,
		float(start[1]) + (float(end[1]) - float(start[1])) * t,
	)


def _apply_seamless_healing_dab(
	poisson_api: PoissonApi,
	source: np.ndarray,
	target: np.ndarray,
	source_center: tuple[float, float],
	target_center: tuple[float, float],
	radius: int,
	opacity: float,
) -> None:
	"""Clone one clipped circular source sample into its target-center position."""
	height, width = target.shape[:2]
	source_x = int(round(source_center[0]))
	source_y = int(round(source_center[1]))
	target_x = int(round(target_center[0]))
	target_y = int(round(target_center[1]))
	offsets = np.arange(-radius, radius + 1)
	valid_x = offsets[
		(0 <= source_x + offsets)
		& (source_x + offsets < width)
		& (0 <= target_x + offsets)
		& (target_x + offsets < width)
	]
	valid_y = offsets[
		(0 <= source_y + offsets)
		& (source_y + offsets < height)
		& (0 <= target_y + offsets)
		& (target_y + offsets < height)
	]
	if valid_x.size == 0 or valid_y.size == 0:
		return
	x0_offset, x1_offset = int(valid_x[0]), int(valid_x[-1]) + 1
	y0_offset, y1_offset = int(valid_y[0]), int(valid_y[-1]) + 1
	source_roi = source[
		source_y + y0_offset:source_y + y1_offset,
		source_x + x0_offset:source_x + x1_offset,
	]
	target_roi = target[
		target_y + y0_offset:target_y + y1_offset,
		target_x + x0_offset:target_x + x1_offset,
	]
	if source_roi.size == 0 or target_roi.size == 0 or source_roi.shape != target_roi.shape:
		return
	mask = _centered_healing_circle_mask(valid_x, valid_y, radius)
	if not np.any(mask > 0):
		return
	target_left = target_x + x0_offset
	target_top = target_y + y0_offset
	clone_center = (
		target_left + source_roi.shape[1] // 2,
		target_top + source_roi.shape[0] // 2,
	)
	try:
		cloned = poisson_api.seamless_clone(
			source_roi,
			target,
			mask,
			clone_center,
			mode=cv2.NORMAL_CLONE,
		)
	except (cv2.error, ValueError) as exc:
		raise RuntimeError(
			f"Healing Brush seamlessClone failed at target center ({target_x}, {target_y})"
		) from exc
	if opacity >= 1.0:
		target[:] = cloned
		return
	cloned_roi = cloned[
		target_top:target_top + source_roi.shape[0],
		target_left:target_left + source_roi.shape[1],
	]
	blended_roi = cv2.addWeighted(cloned_roi, opacity, target_roi, 1.0 - opacity, 0.0)
	target_roi[mask > 0] = blended_roi[mask > 0]


def _centered_healing_circle_mask(
	x_offsets: np.ndarray,
	y_offsets: np.ndarray,
	radius: int,
) -> np.ndarray:
	"""Build a binary circular seamlessClone mask around the dab center point."""
	x_grid = x_offsets.astype(np.float32)[None, :]
	y_grid = y_offsets.astype(np.float32)[:, None]
	circle = x_grid * x_grid + y_grid * y_grid <= float(radius * radius)
	return np.where(circle, 255, 0).astype(np.uint8)


def apply_selection_fill(
	image: np.ndarray,
	mask: np.ndarray,
	color: tuple[int, int, int],
	opacity: float = 1.0,
) -> np.ndarray:
	"""Fill selected pixels on one map image using a rasterized selection mask."""
	if image is None or image.size == 0:
		raise ValueError("image is empty")
	if mask is None or mask.size == 0:
		raise ValueError("mask is empty")
	mask_bool = _normalized_mask(mask, image.shape[:2]) > 0
	result = image.copy()
	if not np.any(mask_bool):
		return result
	color_array = np.asarray(tuple(int(value) for value in color[:3]), dtype=np.float32)
	alpha = float(np.clip(opacity, 0.0, 1.0))
	if alpha >= 1.0:
		result[mask_bool] = color_array.astype(np.uint8)
		return result
	result_float = result.astype(np.float32)
	result_float[mask_bool] = color_array * alpha + result_float[mask_bool] * (1.0 - alpha)
	return np.clip(result_float, 0, 255).astype(np.uint8)


def apply_selection_delete(image: np.ndarray, mask: np.ndarray) -> np.ndarray:
	"""Clear selected pixels on one map image."""
	return apply_selection_fill(image, mask, (0, 0, 0), 1.0)


def _normalized_mask(mask: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
	array = mask
	if array.ndim == 3:
		array = np.max(array[:, :, :3], axis=2)
	if array.shape[:2] != shape:
		raise ValueError("mask size must match image size")
	if array.dtype != np.uint8:
		array = np.clip(array, 0, 255).astype(np.uint8)
	return np.where(array > 0, 255, 0).astype(np.uint8)


class PoissonApi:
	"""Compose selected patches into target images for editing and augmentation."""

	def seamless_clone(
		self,
		source: np.ndarray,
		target: np.ndarray,
		mask: np.ndarray,
		center: tuple[int, int],
		mode: int = cv2.NORMAL_CLONE,
	) -> np.ndarray:
		"""Run OpenCV seamlessClone with validated, contiguous uint8 inputs."""
		source_u8, target_u8, mask_u8 = self._prepare_clone_inputs(source, target, mask)
		self._validate_clone_geometry(source_u8, target_u8, mask_u8, center)
		return cv2.seamlessClone(source_u8, target_u8, mask_u8, center, mode)

	def hard_paste(self, target: np.ndarray, patch: np.ndarray, mask: np.ndarray, x_pos: int, y_pos: int) -> np.ndarray:
		"""Paste only masked patch pixels into a clipped target ROI."""
		patch_u8, target_u8, mask_u8 = self._prepare_clone_inputs(patch, target, mask)
		self._validate_paste_geometry(target_u8, patch_u8, mask_u8, x_pos, y_pos)
		result = target_u8.copy()
		y_slice = slice(y_pos, y_pos + patch_u8.shape[0])
		x_slice = slice(x_pos, x_pos + patch_u8.shape[1])
		roi = result[y_slice, x_slice]
		mask_bool = mask_u8 > 0
		roi[mask_bool] = patch_u8[mask_bool]
		return result

	def detail_preserve_blend(
		self,
		target: np.ndarray,
		patch: np.ndarray,
		mask: np.ndarray,
		x_pos: int,
		y_pos: int,
		feather_sigma: float = 1.5,
		minimum_opacity: float = 0.68,
		adapt_color: bool = True,
		adaptation_strength: float = 0.7,
	) -> np.ndarray:
		"""Blend a defect with local color adaptation while retaining its internal contrast."""
		patch_u8, target_u8, mask_u8 = self._prepare_clone_inputs(patch, target, mask)
		self._validate_paste_geometry(target_u8, patch_u8, mask_u8, x_pos, y_pos)
		binary = (mask_u8 > 0).astype(np.float32)
		if not np.any(binary):
			return target_u8.copy()
		sigma = max(0.0, float(feather_sigma))
		soft = cv2.GaussianBlur(binary, (0, 0), sigma) if sigma > 0 else binary
		floor = float(np.clip(minimum_opacity, 0.0, 1.0))
		result = target_u8.copy()
		roi = result[y_pos:y_pos + patch_u8.shape[0], x_pos:x_pos + patch_u8.shape[1]]
		adapted = patch_u8.astype(np.float32)
		if adapt_color:
			selected = binary > 0
			patch_center = np.median(adapted[selected], axis=0)
			target_center = np.median(roi.astype(np.float32)[selected], axis=0)
			strength = float(np.clip(adaptation_strength, 0.0, 1.0))
			adapted += (target_center - patch_center) * strength
		adapted = np.clip(adapted, 0, 255)
		alpha = np.where(binary > 0, floor + (1.0 - floor) * soft, 0.0)[:, :, None]
		roi[:] = np.clip(adapted * alpha + roi * (1.0 - alpha), 0, 255).astype(np.uint8)
		return result

	def boundary_mixed_blend(
		self,
		target: np.ndarray,
		patch: np.ndarray,
		mask: np.ndarray,
		x_pos: int,
		y_pos: int,
		boundary_ratio: float = 0.15,
	) -> np.ndarray:
		"""Preserve the core and apply Mixed Clone to a patch-relative boundary band."""
		patch_u8, target_u8, mask_u8 = self._prepare_clone_inputs(patch, target, mask)
		self._validate_paste_geometry(target_u8, patch_u8, mask_u8, x_pos, y_pos)
		if not np.any(mask_u8):
			return target_u8.copy()
		radius = self.boundary_radius_for_patch(patch_u8.shape[:2], boundary_ratio)
		core = self._protected_core_mask(mask_u8, radius)
		band = cv2.subtract(mask_u8, core)
		target_roi = target_u8[y_pos:y_pos + patch_u8.shape[0], x_pos:x_pos + patch_u8.shape[1]]
		matched_patch = self._match_patch_tone(patch_u8, target_roi, mask_u8, strength=0.6)
		source_roi = target_roi.copy()
		source_roi[mask_u8 > 0] = matched_patch[mask_u8 > 0]
		center = (x_pos + patch_u8.shape[1] // 2, y_pos + patch_u8.shape[0] // 2)
		try:
			clone_result = self.seamless_clone(source_roi, target_u8, band, center, mode=cv2.MIXED_CLONE)
		except (cv2.error, ValueError):
			clone_result = target_u8
		result = target_u8.copy()
		result_roi = result[y_pos:y_pos + patch_u8.shape[0], x_pos:x_pos + patch_u8.shape[1]]
		clone_roi = clone_result[y_pos:y_pos + patch_u8.shape[0], x_pos:x_pos + patch_u8.shape[1]]
		result_roi[band > 0] = clone_roi[band > 0]
		result_roi[core > 0] = matched_patch[core > 0]
		return result

	@staticmethod
	def _match_patch_tone(
		patch: np.ndarray,
		target_roi: np.ndarray,
		mask: np.ndarray,
		strength: float = 0.6,
		grayscale_threshold: float = 6.0,
	) -> np.ndarray:
		"""Partially match masked patch tone using grayscale or color statistics."""
		selected = mask > 0
		if not np.any(selected):
			return patch.copy()
		amount = float(np.clip(strength, 0.0, 1.0))
		patch_values = patch.astype(np.float32)[selected]
		target_values = target_roi.astype(np.float32)[selected]
		channel_spread = np.mean(np.ptp(patch_values, axis=1))
		matched = patch.astype(np.float32)
		if channel_spread <= float(grayscale_threshold):
			patch_level = float(np.median(cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)[selected]))
			target_level = float(np.median(cv2.cvtColor(target_roi, cv2.COLOR_BGR2GRAY)[selected]))
			matched[selected] += (target_level - patch_level) * amount
		else:
			patch_center = np.median(patch_values, axis=0)
			target_center = np.median(target_values, axis=0)
			matched[selected] += (target_center - patch_center) * amount
		return np.clip(matched, 0, 255).astype(np.uint8)

	@staticmethod
	def boundary_radius_for_patch(
		patch_shape: tuple[int, int],
		ratio: float = 0.05,
		minimum: int = 2,
		maximum: int = 255,
	) -> int:
		"""Convert a patch-size ratio into a safely bounded boundary radius."""
		height, width = patch_shape[:2]
		if height <= 0 or width <= 0:
			raise ValueError("patch size must be positive")
		lower = max(1, int(minimum))
		upper = max(lower, int(maximum))
		pixels = int(round(min(height, width) * max(0.0, float(ratio))))
		return min(upper, max(lower, pixels))

	@staticmethod
	def _protected_core_mask(mask: np.ndarray, erosion_radius: int) -> np.ndarray:
		"""Keep most defect pixels, capping the boundary by local defect thickness."""
		binary = np.where(mask > 0, 255, 0).astype(np.uint8)
		padded = cv2.copyMakeBorder(binary, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
		distance = cv2.distanceTransform(padded, cv2.DIST_L2, 3)[1:-1, 1:-1]
		maximum = float(distance.max())
		if maximum <= 0:
			return np.zeros_like(mask)
		edge_width = min(max(1.0, float(erosion_radius)), maximum * 0.25)
		core = np.where(distance > edge_width, 255, 0).astype(np.uint8)
		if np.any(core):
			return core
		return np.where(distance >= maximum * 0.75, 255, 0).astype(np.uint8)

	def poisson_blend(
		self,
		target: np.ndarray,
		patch: np.ndarray,
		x_pos: int,
		y_pos: int,
		mask: np.ndarray | None = None,
		mode: int = cv2.NORMAL_CLONE,
		fallback: bool = True,
	) -> np.ndarray:
		"""Blend one patch and optionally fall back to masked paste on clone failure."""
		if mask is None:
			mask = make_nonzero_mask(patch)
		if mask is None or mask.size == 0 or not np.any(mask):
			return target.copy()
		center = (int(x_pos + patch.shape[1] // 2), int(y_pos + patch.shape[0] // 2))
		try:
			return self.seamless_clone(patch, target, mask, center, mode=mode)
		except (cv2.error, ValueError) as exc:
			if not fallback:
				raise RuntimeError(f"OpenCV seamlessClone failed: {exc}") from exc
			return self.hard_paste(target, patch, mask, int(x_pos), int(y_pos))

	def compose_patch(
		self,
		target: np.ndarray,
		patch: np.ndarray,
		mask: np.ndarray,
		x_pos: int,
		y_pos: int,
		mode: int = cv2.NORMAL_CLONE,
		fallback: bool = True,
	) -> np.ndarray:
		"""Validate placement and compose a Dataset Studio patch into a target image."""
		patch_u8, target_u8, mask_u8 = self._prepare_clone_inputs(patch, target, mask)
		self._validate_paste_geometry(target_u8, patch_u8, mask_u8, x_pos, y_pos)
		return self.poisson_blend(
			target_u8,
			patch_u8,
			int(x_pos),
			int(y_pos),
			mask_u8,
			mode=mode,
			fallback=fallback,
		)

	def _prepare_clone_inputs(
		self,
		source: np.ndarray,
		target: np.ndarray,
		mask: np.ndarray,
	) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
		source_u8 = self._as_bgr_u8(source, "source")
		target_u8 = self._as_bgr_u8(target, "target")
		mask_u8 = self._as_mask_u8(mask, source_u8.shape[:2])
		return source_u8, target_u8, mask_u8

	def _as_bgr_u8(self, image: np.ndarray, name: str) -> np.ndarray:
		if image is None or image.size == 0:
			raise ValueError(f"{name} image is empty")
		array = image
		if array.ndim == 2:
			array = cv2.cvtColor(array, cv2.COLOR_GRAY2BGR)
		elif array.ndim == 3 and array.shape[2] == 4:
			array = cv2.cvtColor(array, cv2.COLOR_BGRA2BGR)
		elif array.ndim != 3 or array.shape[2] != 3:
			raise ValueError(f"{name} image must be grayscale, BGR, or BGRA")
		if array.dtype != np.uint8:
			array = np.clip(array, 0, 255).astype(np.uint8)
		return np.ascontiguousarray(array)

	def _as_mask_u8(self, mask: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
		if mask is None or mask.size == 0:
			raise ValueError("mask is empty")
		array = mask
		if array.ndim == 3:
			array = np.max(array[:, :, :3], axis=2)
		if array.shape[:2] != shape:
			raise ValueError("mask size must match patch size")
		if array.dtype != np.uint8:
			array = np.clip(array, 0, 255).astype(np.uint8)
		return np.ascontiguousarray(np.where(array > 0, 255, 0).astype(np.uint8))

	def _validate_clone_geometry(
		self,
		source: np.ndarray,
		target: np.ndarray,
		mask: np.ndarray,
		center: tuple[int, int],
	) -> None:
		if mask.shape[:2] != source.shape[:2]:
			raise ValueError("source and mask sizes must match")
		left = int(center[0] - source.shape[1] // 2)
		top = int(center[1] - source.shape[0] // 2)
		self._validate_paste_geometry(target, source, mask, left, top)

	def _validate_paste_geometry(
		self,
		target: np.ndarray,
		patch: np.ndarray,
		mask: np.ndarray,
		x_pos: int,
		y_pos: int,
	) -> None:
		if mask.shape[:2] != patch.shape[:2]:
			raise ValueError("patch and mask sizes must match")
		if x_pos < 0 or y_pos < 0:
			raise ValueError("patch placement must be non-negative")
		if x_pos + patch.shape[1] > target.shape[1] or y_pos + patch.shape[0] > target.shape[0]:
			raise ValueError("patch placement is outside the target image")
