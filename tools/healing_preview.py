"""Serial, replaceable healing previews isolated from committed canvas pixels."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QImage

from core.geometry import HealingStroke
from core.qt_image import bgr_to_qpixmap, qimage_to_bgr
from service.editing_service import apply_healing_strokes


@dataclass
class HealingPreviewSession:
    """Freeze source pixels and brush settings for one gesture."""

    image: QImage
    size: int
    opacity: float
    pixels: np.ndarray | None = None


def render_healing_preview(session: HealingPreviewSession, strokes: list[HealingStroke]) -> np.ndarray:
    """Use precisely the service used by EditingWorker, without GUI access."""
    if session.pixels is None:
        session.pixels = qimage_to_bgr(session.image)
    return apply_healing_strokes(session.pixels, strokes, session.size, session.opacity)


class HealingPreviewController(QObject):
    """Run one solve and retain only the newest cumulative stroke snapshot."""

    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="healing-preview")
        executor = self._executor
        canvas.destroyed.connect(lambda: executor.shutdown(wait=False, cancel_futures=True))
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._poll)
        self._session = self._pending = self._running = self._future = None
        self._image_key = None
        self._committing = self._closed = False
        self._requested_count = 0

    def begin(self, size: int, opacity: float) -> None:
        """Capture implicitly shared image data without modifying Undo or pixels."""
        self.clear()
        if not self._closed:
            self._image_key = self.canvas.pixmap.cacheKey()
            self._session = HealingPreviewSession(self.canvas.pixmap.toImage(), size, opacity)

    def request(self, strokes: list[HealingStroke]) -> None:
        """Coalesce append-only path updates; never enqueue unbounded work."""
        if self._session is None or self._closed or len(strokes) == self._requested_count:
            return
        self._requested_count = len(strokes)
        self._pending = (self._session, list(strokes))
        self.canvas.healing_preview_status = "힐링 브러시 · 합성 계산 중"
        self.canvas.update()
        self._start_pending()
        self._timer.start()

    def mark_committing(self) -> None:
        self._committing = True
        self.canvas.healing_preview_status = "힐링 브러시 · 적용 중"
        self.canvas.update()

    def clear(self) -> None:
        """Invalidate in-flight results without waiting for the native solve."""
        self._session = self._pending = self._image_key = None
        self._requested_count = 0
        self._committing = False
        self.canvas.clear_healing_preview()
        if self._future is None:
            self._timer.stop()

    def close(self) -> None:
        self.clear()
        self._closed = True
        self._timer.stop()
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _start_pending(self) -> None:
        if self._future is None and self._pending is not None:
            self._running, self._pending = self._pending, None
            self._future = self._executor.submit(render_healing_preview, *self._running)

    def _poll(self) -> None:
        if self._future is None or not self._future.done():
            return
        session, strokes = self._running
        future, self._future = self._future, None
        self._running = None
        current = session is self._session and self.canvas.pixmap.cacheKey() == self._image_key
        try:
            pixels = future.result()
        except Exception as error:
            if current:
                self.canvas.clear_healing_preview()
                self.canvas.healing_preview_status = f"힐링 미리보기 실패: {error}"
                self.canvas.update()
        else:
            if current:
                # An older prefix is valid progress within this same append-only
                # gesture, but never label it as the completed/current result.
                status = "적용 중" if self._committing else "합성 계산 중" if len(strokes) < self._requested_count else "최종 합성 미리보기"
                self.canvas.healing_preview_pixmap = bgr_to_qpixmap(pixels)
                self.canvas.healing_preview_status = f"힐링 브러시 · {status}"
                self.canvas.update()
        self._start_pending()
        if self._future is None:
            self._timer.stop()
