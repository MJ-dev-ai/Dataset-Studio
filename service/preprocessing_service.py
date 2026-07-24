from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from core.mask_ops import morphology

@dataclass(frozen=True)
class PreprocessOptions:
	"""Stores geometry and intensity options for one preprocessing run."""

	resize_enabled: bool = False
	width: int = 0
	height: int = 0
	flip_horizontal: bool = False
	flip_vertical: bool = False
	rotation_degrees: float = 0.0
	brightness_shift: int = 0
	contrast_shift: int = 0

class PreprocessApi:
	"""Preprocessing functions exposed to UI and workers."""

	def apply_clahe(self, image: np.ndarray, clip_limit: float = 2.0) -> np.ndarray:
		return apply_clahe(image, clip_limit=clip_limit)

	def resize(self, image: np.ndarray, size: tuple[int, int]) -> np.ndarray:
		return cv2.resize(image, size, interpolation=cv2.INTER_AREA)

	def threshold(self, image: np.ndarray, mode: str = "manual", value: int = 127, invert: bool = False) -> np.ndarray:
		if mode == "otsu":
			return otsu_threshold(image, invert=invert)
		return threshold(image, value=value, invert=invert)

	def morphology(self, mask: np.ndarray, operation: str, kernel_size: int, iterations: int = 1) -> np.ndarray:
		return morphology(mask, operation, kernel_size, iterations)

	def apply_options(self, image: np.ndarray, options: PreprocessOptions | dict) -> tuple[np.ndarray, np.ndarray]:
		"""Apply resize, flip, rotation, and brightness while returning the label affine matrix."""
		config = _coerce_options(options)
		if image is None:
			raise ValueError("Preprocessing input image is None.")
		result = np.ascontiguousarray(image)
		if result.ndim not in {2, 3}:
			raise ValueError(f"Unsupported image shape: {result.shape}")
		if result.dtype != np.uint8:
			result = to_uint8(result)

		source_height, source_width = result.shape[:2]
		matrix = np.eye(3, dtype=np.float32)
		current_width, current_height = source_width, source_height

		if config.resize_enabled:
			target_width = max(1, int(config.width))
			target_height = max(1, int(config.height))
			result = cv2.resize(result, (target_width, target_height), interpolation=cv2.INTER_AREA)
			scale = np.array(
				[
					[target_width / max(1.0, float(current_width)), 0.0, 0.0],
					[0.0, target_height / max(1.0, float(current_height)), 0.0],
					[0.0, 0.0, 1.0],
				],
				dtype=np.float32,
			)
			matrix = scale @ matrix
			current_width, current_height = target_width, target_height

		if config.flip_horizontal or config.flip_vertical:
			flip_code = -1 if config.flip_horizontal and config.flip_vertical else 1 if config.flip_horizontal else 0
			result = cv2.flip(result, flip_code)
			flip = np.eye(3, dtype=np.float32)
			if config.flip_horizontal:
				flip[0, 0] = -1.0
				flip[0, 2] = float(current_width)
			if config.flip_vertical:
				flip[1, 1] = -1.0
				flip[1, 2] = float(current_height)
			matrix = flip @ matrix

		brightness = int(config.brightness_shift)
		contrast = int(config.contrast_shift)
		if brightness or contrast:
			alpha = 1.0 + float(contrast) / 100.0
			result = np.clip(
				result.astype(np.float32) * alpha + float(brightness),
				0,
				255,
			).astype(np.uint8)

		angle = float(config.rotation_degrees)
		if abs(angle) > 1e-6:
			center = ((current_width - 1) * 0.5, (current_height - 1) * 0.5)
			rotation_2x3 = cv2.getRotationMatrix2D(center, angle, 1.0).astype(np.float32)
			result = cv2.warpAffine(
				result,
				rotation_2x3,
				(current_width, current_height),
				flags=cv2.INTER_LINEAR,
				borderMode=cv2.BORDER_CONSTANT,
				borderValue=0,
			)
			rotation = np.eye(3, dtype=np.float32)
			rotation[:2, :] = rotation_2x3
			matrix = rotation @ matrix

		return np.ascontiguousarray(result), matrix

def _coerce_options(options: PreprocessOptions | dict) -> PreprocessOptions:
	if isinstance(options, PreprocessOptions):
		return options
	return PreprocessOptions(
		resize_enabled=bool(options.get("resize_enabled", False)),
		width=int(options.get("width", 0)),
		height=int(options.get("height", 0)),
		flip_horizontal=bool(options.get("flip_horizontal", False)),
		flip_vertical=bool(options.get("flip_vertical", False)),
		rotation_degrees=float(options.get("rotation_degrees", 0.0)),
		brightness_shift=int(options.get("brightness_shift", 0)),
		contrast_shift=int(options.get("contrast_shift", 0)),
	)


def apply_clahe(image: np.ndarray, clip_limit: float = 2.0, tile_grid_size: tuple[int, int] = (8, 8)) -> np.ndarray:
	clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)
	if image.ndim == 2:
		return clahe.apply(image)
	lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
	lab[:, :, 0] = clahe.apply(lab[:, :, 0])
	return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def threshold(image: np.ndarray, value: int = 127, invert: bool = False) -> np.ndarray:
	gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
	threshold_type = cv2.THRESH_BINARY_INV if invert else cv2.THRESH_BINARY
	_ret, result = cv2.threshold(gray, value, 255, threshold_type)
	return result


def otsu_threshold(image: np.ndarray, invert: bool = False) -> np.ndarray:
	gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
	threshold_type = cv2.THRESH_BINARY_INV if invert else cv2.THRESH_BINARY
	_ret, result = cv2.threshold(gray, 0, 255, threshold_type | cv2.THRESH_OTSU)
	return result


def to_uint8(image: np.ndarray) -> np.ndarray:
	minimum = float(np.min(image))
	maximum = float(np.max(image))
	if maximum <= minimum:
		return np.zeros(image.shape[:2], dtype=np.uint8) if image.ndim == 2 else np.zeros(image.shape, dtype=np.uint8)
	return np.clip((image.astype(np.float32) - minimum) / (maximum - minimum) * 255.0, 0, 255).astype(np.uint8)
