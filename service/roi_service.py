"""Auto ROI reference image and contour utilities.

Author: TNS AI
"""

from __future__ import annotations

import cv2
import numpy as np


def roi_contour(
	source,
	*,
	mode: str = "auto",
	image_shape: tuple[int, int] | None = None,
) -> tuple[tuple[tuple[float, float], ...], ...]:
	"""Return normalized ROI contours from selection points or an auto reference image."""
	if mode == "selection":
		return normalize_roi_contours(source, image_shape=image_shape)
	if mode != "auto":
		raise ValueError(f"Unsupported ROI contour mode: {mode}")
	points = detect_auto_roi_contour(source)
	if not points:
		return tuple()
	return normalize_roi_contours((tuple(points),), image_shape=image_shape)


def normalize_roi_contours(
	contours,
	*,
	image_shape: tuple[int, int] | None = None,
) -> tuple[tuple[tuple[float, float], ...], ...]:
	"""Return ROI contours as clamped float point tuples."""
	width = None
	height = None
	if image_shape is not None:
		height = float(max(1, int(image_shape[0])))
		width = float(max(1, int(image_shape[1])))
	normalized = []
	for contour in contours or []:
		points = []
		for point in contour or []:
			if not isinstance(point, (list, tuple, np.ndarray)) or len(point) < 2:
				continue
			x = float(point[0])
			y = float(point[1])
			if width is not None:
				x = float(np.clip(x, 0.0, width))
			if height is not None:
				y = float(np.clip(y, 0.0, height))
			if not points or abs(points[-1][0] - x) > 1e-3 or abs(points[-1][1] - y) > 1e-3:
				points.append((x, y))
		if len(points) >= 2 and abs(points[0][0] - points[-1][0]) < 1e-3 and abs(points[0][1] - points[-1][1]) < 1e-3:
			points.pop()
		if len(points) >= 3:
			normalized.append(tuple(points))
	return tuple(normalized)


def detect_auto_roi_contour(image: np.ndarray | list[np.ndarray] | tuple[np.ndarray, ...]) -> list[tuple[float, float]] | None:
	"""Return the dominant product ROI contour using threshold-based segmentation."""
	try:
		gray = build_auto_roi_reference(image)
	except ValueError:
		return None
	if gray.size == 0:
		return None

	height, width = gray.shape[:2]
	max_side = 1024
	scale = min(1.0, max_side / max(width, height))
	if scale < 1.0:
		small = cv2.resize(
			gray,
			(max(1, int(round(width * scale))), max(1, int(round(height * scale)))),
			interpolation=cv2.INTER_AREA,
		)
	else:
		small = gray

	blurred = cv2.GaussianBlur(small, (7, 7), 0)
	contour = _largest_threshold_contour(blurred)
	if contour is None:
		return None

	hull = cv2.convexHull(contour)
	epsilon = max(2.0, 0.004 * cv2.arcLength(hull, True))
	approx = cv2.approxPolyDP(hull, epsilon, True)
	points = approx.reshape(-1, 2).astype(np.float32)
	if scale < 1.0:
		points[:, 0] /= scale
		points[:, 1] /= scale

	return [(float(x), float(y)) for x, y in points]


def build_reference_image(images: list[np.ndarray]) -> np.ndarray:
	"""Build a stable grayscale reference from four photometric source images.

	Args:
		images (list[np.ndarray]): Input image sequence.

	Returns:
		np.ndarray: Grayscale reference image.
	"""
	gray_images = _validated_gray_images(images)
	stack = np.stack(gray_images, axis=0).astype(np.float32)
	median_image = np.median(stack, axis=0)
	max_image = np.max(stack, axis=0)
	return np.clip(median_image * 0.70 + max_image * 0.30, 0, 255).astype(
		np.uint8
	)


def build_auto_roi_reference(image: np.ndarray | list[np.ndarray] | tuple[np.ndarray, ...]) -> np.ndarray:
	"""Build the grayscale image used by Auto ROI detection."""
	if isinstance(image, (list, tuple)):
		if len(image) >= 4:
			return build_reference_image(list(image[:4]))
		if len(image) == 1:
			return _to_gray_u8(image[0])
		raise ValueError("Auto ROI requires one image or four reference images.")
	return _to_gray_u8(image)


def _largest_threshold_contour(gray: np.ndarray) -> np.ndarray | None:
	if gray.size == 0:
		return None

	threshold_variants = []
	_, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
	threshold_variants.append(otsu)
	threshold_variants.append(cv2.bitwise_not(otsu))
	adaptive = cv2.adaptiveThreshold(
		gray,
		255,
		cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
		cv2.THRESH_BINARY,
		51,
		2,
	)
	threshold_variants.append(adaptive)
	threshold_variants.append(cv2.bitwise_not(adaptive))

	best_contour = None
	best_score = -1.0
	image_h, image_w = gray.shape[:2]
	image_area = float(image_h * image_w)
	image_center = np.array([image_w / 2.0, image_h / 2.0], dtype=np.float32)
	kernel_size = max(9, int(round(min(image_h, image_w) * 0.02)))
	if kernel_size % 2 == 0:
		kernel_size += 1
	kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))

	for binary in threshold_variants:
		cleaned = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
		cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel, iterations=1)
		contours, _hierarchy = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
		for contour in contours:
			area = float(cv2.contourArea(contour))
			if area < image_area * 0.05 or area > image_area * 0.98:
				continue
			x, y, w, h = cv2.boundingRect(contour)
			aspect = max(float(w), float(h)) / max(1.0, min(float(w), float(h)))
			if aspect < 1.1 or aspect > 8.0:
				continue
			moments = cv2.moments(contour)
			if abs(moments.get("m00", 0.0)) < 1e-6:
				continue
			center = np.array([moments["m10"] / moments["m00"], moments["m01"] / moments["m00"]], dtype=np.float32)
			center_penalty = float(np.linalg.norm(center - image_center) / max(image_h, image_w))
			score = area * max(0.1, 1.0 - center_penalty)
			if score > best_score:
				best_score = score
				best_contour = contour
	return best_contour


def _validated_gray_images(images: list[np.ndarray]) -> list[np.ndarray]:
	if images is None or len(images) < 4:
		raise ValueError("Photometric reference requires four input images.")

	gray_images = [_to_gray_u8(image) for image in images[:4]]
	expected_shape = gray_images[0].shape
	if any(gray.shape != expected_shape for gray in gray_images[1:]):
		raise ValueError("Photometric images must have identical dimensions.")
	return gray_images


def _to_gray_u8(image: np.ndarray) -> np.ndarray:
	if image is None:
		raise ValueError("Photometric input contains None.")
	if image.ndim == 2:
		gray = image
	elif image.ndim == 3 and image.shape[2] == 3:
		gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
	elif image.ndim == 3 and image.shape[2] == 4:
		gray = cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
	else:
		raise ValueError(f"Unsupported image shape: {image.shape}")

	if gray.dtype == np.uint8:
		return np.ascontiguousarray(gray)
	return cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
