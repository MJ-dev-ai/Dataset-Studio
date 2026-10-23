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


def patch_mode_from_text(value: str) -> int | str | None:
	"""Resolve the mode shared by live preview and Apply Blend."""
	modes = {"Detail Preserve": None, "Boundary Mixed": "boundary_mixed", "Hard Paste": "hard_paste"}
	return modes[value] if value in modes else clone_mode_from_text(value)


def compose_patch_mode(
	target: np.ndarray, patch: np.ndarray, mask: np.ndarray,
	x_pos: int, y_pos: int, mode: int | str | None, map_key: str = "",
) -> np.ndarray:
	"""Compose preview and committed pixels with identical map-specific rules.

	Inputs are borrowed read-only; every algorithm returns an owned result.
	Normal maps skip Detail Preserve color adaptation in both paths.
	"""
	if mode == "boundary_mixed":
		return boundary_mixed_blend(target, patch, mask, x_pos, y_pos)
	if mode == "hard_paste":
		return hard_paste(target, patch, mask, x_pos, y_pos)
	if mode is None:
		return detail_preserve_blend(target, patch, mask, x_pos, y_pos, adapt_color="normal" not in map_key.casefold())
	return compose_patch(target, patch, mask, x_pos, y_pos, mode=mode, fallback=False)


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
	bgr = tuple(int(value) for value in color[:3])
	thickness = max(1, int(size))
	if not strokes:
		return result
	points = [(int(round(p[0])), int(round(p[1]))) for stroke in strokes for p in stroke]
	padding = thickness + 2
	left = max(0, min(p[0] for p in points) - padding)
	top = max(0, min(p[1] for p in points) - padding)
	right = min(image.shape[1], max(p[0] for p in points) + padding + 1)
	bottom = min(image.shape[0], max(p[1] for p in points) + padding + 1)
	if right <= left or bottom <= top:
		return result
	roi = result[top:bottom, left:right]
	overlay = roi.copy()
	for start, end in strokes:
		cv2.line(
			overlay,
			(int(round(start[0])) - left, int(round(start[1])) - top),
			(int(round(end[0])) - left, int(round(end[1])) - top),
			bgr,
			thickness=thickness,
			lineType=cv2.LINE_8,
		)
	alpha = float(np.clip(opacity, 0.0, 1.0))
	if alpha >= 1.0:
		roi[:] = overlay
	else:
		roi[:] = cv2.addWeighted(overlay, alpha, roi, 1.0 - alpha, 0.0)
	return result


def apply_healing_strokes(
	image: np.ndarray,
	strokes: list[HealingStroke],
	size: int,
	opacity: float = 1.0,
	source_image: np.ndarray | None = None,
	*,
	inplace: bool = False,
	check_cancelled: Callable[[], None] | None = None,
) -> np.ndarray:
	"""Heal one sampled gesture with a union mask and one NORMAL_CLONE solve.

	Sampling uses the unchanged source image. Opacity is applied once per
	gesture, so repeated input events cannot darken overlapping brush marks.
	Source/target offsets must remain fixed throughout the gesture.
	"""
	if image is None or image.size == 0:
		raise ValueError("image is empty")
	result = image if inplace else image.copy()
	if not strokes or opacity <= 0:
		return result
	source = image if source_image is None else source_image
	if source.shape != image.shape:
		raise ValueError("source image size must match target image size")
	if check_cancelled is not None:
		check_cancelled()
	region = _healing_stroke_region(strokes, size, image.shape[:2])
	if region is None:
		return result
	mask, x, y, dx, dy = region
	h, w = mask.shape
	patch = source[y + dy:y + dy + h, x + dx:x + dx + w]
	if check_cancelled is not None:
		check_cancelled()
	cloned = seamless_clone(patch, image, mask, (x + w // 2, y + h // 2), mode=cv2.NORMAL_CLONE)
	if check_cancelled is not None:
		check_cancelled()
	roi = result[y:y + h, x:x + w]
	alpha = min(1.0, float(opacity))
	blended = cv2.addWeighted(cloned[y:y + h, x:x + w], alpha, roi, 1.0 - alpha, 0)
	roi[mask > 0] = blended[mask > 0]
	return result


def _healing_stroke_region(strokes: list[HealingStroke], size: int, shape: tuple[int, int]):
	"""Rasterize round brush coverage clipped to valid source AND target pixels."""
	points = np.asarray(strokes, dtype=np.float64)
	if points.ndim != 3 or points.shape[1:] != (4, 2) or not np.isfinite(points).all():
		raise ValueError("Healing strokes must contain finite source and target point pairs")
	offsets = points[:, :2] - points[:, 2:]
	dx, dy = (int(round(v)) for v in offsets[0, 0])
	if not np.allclose(offsets, offsets[0, 0], rtol=0, atol=1e-6):
		raise ValueError("Healing source offset must remain fixed within one gesture")
	radius = max(1, int(round(size / 2.0)))
	targets = np.rint(points[:, 2:]).astype(np.int64)
	height, width = shape
	x = max(0, -dx, int(targets[:, :, 0].min()) - radius - 1)
	y = max(0, -dy, int(targets[:, :, 1].min()) - radius - 1)
	right = min(width, width - dx, int(targets[:, :, 0].max()) + radius + 2)
	bottom = min(height, height - dy, int(targets[:, :, 1].max()) + radius + 2)
	if right <= x or bottom <= y:
		return None
	mask = np.zeros((bottom - y, right - x), np.uint8)
	for start, end in targets:
		p1 = (int(start[0]) - x, int(start[1]) - y)
		p2 = (int(end[0]) - x, int(end[1]) - y)
		cv2.line(mask, p1, p2, 255, thickness=radius * 2, lineType=cv2.LINE_8)
	# A sub-three-pixel overlap has no interior for Poisson reconstruction.
	_, _, mw, mh = cv2.boundingRect(mask)
	return (mask, x, y, dx, dy) if mw >= 3 and mh >= 3 else None


def apply_healing_to_images(
	images: Mapping[str, np.ndarray],
	strokes: list[HealingStroke],
	size: int,
	opacity: float = 1.0,
	*,
	check_cancelled: Callable[[], None] | None = None,
	progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, np.ndarray]:
	"""Apply one healing brush gesture to a keyed MapSet image collection."""
	results: dict[str, np.ndarray] = {}
	total = len(images)
	if total == 0 or not strokes:
		return results
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
		)
		if progress is not None:
			progress(index, total, key)
	return results


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


def seamless_clone(
	source: np.ndarray,
	target: np.ndarray,
	mask: np.ndarray,
	center: tuple[int, int],
	mode: int = cv2.NORMAL_CLONE,
) -> np.ndarray:
	"""Clone at the full source center, correcting OpenCV's mask-bounds centering.

	Keep pixels outside the selection exact and restrict the solver output to a
	local destination. Padding preserves masks that touch the source image edge.
	"""
	source_u8, target_u8, mask_u8 = _prepare_clone_inputs(source, target, mask)
	_validate_clone_geometry(source_u8, target_u8, mask_u8, center)
	result = target_u8.copy()
	if not np.any(mask_u8):
		return result
	left = int(center[0] - source_u8.shape[1] // 2)
	top = int(center[1] - source_u8.shape[0] // 2)
	height, width = source_u8.shape[:2]
	x0, y0 = max(0, left - 2), max(0, top - 2)
	x1, y1 = min(target_u8.shape[1], left + width + 2), min(target_u8.shape[0], top + height + 2)
	mx, my, mw, mh = cv2.boundingRect(mask_u8)
	clone_center = (left - x0 + mx + mw // 2, top - y0 + my + mh // 2)
	source_pad = cv2.copyMakeBorder(source_u8, 1, 1, 1, 1, cv2.BORDER_REPLICATE)
	mask_pad = cv2.copyMakeBorder(mask_u8, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
	cloned = cv2.seamlessClone(source_pad, target_u8[y0:y1, x0:x1].copy(), mask_pad, clone_center, mode)
	roi = result[top:top + height, left:left + width]
	cloned_roi = cloned[top - y0:top - y0 + height, left - x0:left - x0 + width]
	roi[mask_u8 > 0] = cloned_roi[mask_u8 > 0]
	return result

def hard_paste(target: np.ndarray, patch: np.ndarray, mask: np.ndarray, x_pos: int, y_pos: int) -> np.ndarray:
	"""Paste only masked patch pixels into a clipped target ROI."""
	patch_u8, target_u8, mask_u8 = _prepare_clone_inputs(patch, target, mask)
	_validate_paste_geometry(target_u8, patch_u8, mask_u8, x_pos, y_pos)
	result = target_u8.copy()
	y_slice = slice(y_pos, y_pos + patch_u8.shape[0])
	x_slice = slice(x_pos, x_pos + patch_u8.shape[1])
	roi = result[y_slice, x_slice]
	mask_bool = mask_u8 > 0
	roi[mask_bool] = patch_u8[mask_bool]
	return result

def detail_preserve_blend(
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
	patch_u8, target_u8, mask_u8 = _prepare_clone_inputs(patch, target, mask)
	_validate_paste_geometry(target_u8, patch_u8, mask_u8, x_pos, y_pos)
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
	target: np.ndarray,
	patch: np.ndarray,
	mask: np.ndarray,
	x_pos: int,
	y_pos: int,
	boundary_ratio: float = 0.15,
) -> np.ndarray:
	"""Preserve the core and apply Mixed Clone to a patch-relative boundary band."""
	patch_u8, target_u8, mask_u8 = _prepare_clone_inputs(patch, target, mask)
	_validate_paste_geometry(target_u8, patch_u8, mask_u8, x_pos, y_pos)
	if not np.any(mask_u8):
		return target_u8.copy()
	radius = boundary_radius_for_patch(patch_u8.shape[:2], boundary_ratio)
	core = _protected_core_mask(mask_u8, radius)
	band = cv2.subtract(mask_u8, core)
	target_roi = target_u8[y_pos:y_pos + patch_u8.shape[0], x_pos:x_pos + patch_u8.shape[1]]
	matched_patch = _match_patch_tone(patch_u8, target_roi, mask_u8, strength=0.6)
	source_roi = target_roi.copy()
	source_roi[mask_u8 > 0] = matched_patch[mask_u8 > 0]
	center = (x_pos + patch_u8.shape[1] // 2, y_pos + patch_u8.shape[0] // 2)
	try:
		clone_result = seamless_clone(source_roi, target_u8, band, center, mode=cv2.MIXED_CLONE)
	except (cv2.error, ValueError):
		clone_result = target_u8
	result = target_u8.copy()
	result_roi = result[y_pos:y_pos + patch_u8.shape[0], x_pos:x_pos + patch_u8.shape[1]]
	clone_roi = clone_result[y_pos:y_pos + patch_u8.shape[0], x_pos:x_pos + patch_u8.shape[1]]
	result_roi[band > 0] = clone_roi[band > 0]
	result_roi[core > 0] = matched_patch[core > 0]
	return result

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
		return seamless_clone(patch, target, mask, center, mode=mode)
	except (cv2.error, ValueError) as exc:
		if not fallback:
			raise RuntimeError(f"OpenCV seamlessClone failed: {exc}") from exc
		return hard_paste(target, patch, mask, int(x_pos), int(y_pos))

def compose_patch(
	target: np.ndarray,
	patch: np.ndarray,
	mask: np.ndarray,
	x_pos: int,
	y_pos: int,
	mode: int = cv2.NORMAL_CLONE,
	fallback: bool = True,
) -> np.ndarray:
	"""Validate placement and compose a Dataset Studio patch into a target image."""
	patch_u8, target_u8, mask_u8 = _prepare_clone_inputs(patch, target, mask)
	_validate_paste_geometry(target_u8, patch_u8, mask_u8, x_pos, y_pos)
	return poisson_blend(
		target_u8,
		patch_u8,
		int(x_pos),
		int(y_pos),
		mask_u8,
		mode=mode,
		fallback=fallback,
	)

def _prepare_clone_inputs(
	source: np.ndarray,
	target: np.ndarray,
	mask: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
	source_u8 = _as_bgr_u8(source, "source")
	target_u8 = _as_bgr_u8(target, "target")
	mask_u8 = _as_mask_u8(mask, source_u8.shape[:2])
	return source_u8, target_u8, mask_u8

def _as_bgr_u8(image: np.ndarray, name: str) -> np.ndarray:
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

def _as_mask_u8(mask: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
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
	source: np.ndarray,
	target: np.ndarray,
	mask: np.ndarray,
	center: tuple[int, int],
) -> None:
	if mask.shape[:2] != source.shape[:2]:
		raise ValueError("source and mask sizes must match")
	left = int(center[0] - source.shape[1] // 2)
	top = int(center[1] - source.shape[0] // 2)
	_validate_paste_geometry(target, source, mask, left, top)

def _validate_paste_geometry(
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

