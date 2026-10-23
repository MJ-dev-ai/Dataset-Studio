"""Latest-only patch preview; workers own pixels, the GUI owns Qt widgets."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QImage

from core.qt_image import bgr_to_qpixmap, qimage_to_bgr
from service.editing_service import compose_patch_mode
from tools.patch_tools import PatchPreview


@dataclass
class PreviewTarget:
    """Implicitly shared image snapshot, converted once on the serial worker."""

    image: QImage
    pixels: np.ndarray | None = None


def render_patch_preview(target: PreviewTarget, patch: PatchPreview, mode: int | str | None, map_key: str) -> np.ndarray:
    """Return the exact committed patch rectangle at native resolution.

    The transformed patch arrays are immutable cache results retained by the
    request. No QPixmap or widget is accessed here, even during window teardown.
    """
    if target.pixels is None:
        target.pixels = qimage_to_bgr(target.image)
    result = compose_patch_mode(target.pixels, patch.patch, patch.mask, patch.x_pos, patch.y_pos, mode, map_key)
    h, w = patch.patch.shape[:2]
    return result[patch.y_pos:patch.y_pos + h, patch.x_pos:patch.x_pos + w].copy()


class PatchPreviewController(QObject):
    """Keep one running job and replace the pending job on every change.

    Polling futures avoids callbacks into deleted Qt objects. Invalidating a
    request never waits for OpenCV; its result is simply no longer eligible.
    """

    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="patch-preview")
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._poll)
        self._future = None
        self._running = None
        self._pending = None
        self._key = None
        self._target_key = None
        self._target = None
        self._closed = False
        # This closure owns only the executor, never a widget or this QObject.
        executor = self._executor
        canvas.destroyed.connect(lambda: executor.shutdown(wait=False, cancel_futures=True))

    def request(self, key: tuple, patch: PatchPreview, mode: int | str | None, map_key: str, label: str) -> bool:
        """Queue a new snapshot; return False for an already requested state."""
        if self._closed or key == self._key:
            return False
        self._key = key
        image_key = self.canvas.pixmap.cacheKey()
        if image_key != self._target_key:
            self._target = PreviewTarget(self.canvas.pixmap.toImage())
            self._target_key = image_key
        self._pending = (key, self._target, patch, mode, map_key, label)
        self.canvas.patch_preview_status = f"{label} · 합성 계산 중 (위치 안내)"
        self._start_pending()
        self._timer.start()
        return True

    def clear(self) -> None:
        """Invalidate active/pending work without blocking the event loop."""
        self._key = self._pending = self._target = self._target_key = None
        self.canvas.clear_patch_preview()
        if self._future is None:
            self._timer.stop()

    def close(self) -> None:
        """Stop accepting work; in-flight pixel computation may finish safely."""
        self.clear()
        self._closed = True
        self._timer.stop()
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _start_pending(self) -> None:
        if self._future is not None or self._pending is None:
            return
        self._running, self._pending = self._pending, None
        _, target, patch, mode, map_key, _ = self._running
        self._future = self._executor.submit(render_patch_preview, target, patch, mode, map_key)

    def _poll(self) -> None:
        if self._future is None or not self._future.done():
            return
        key, _, patch, _, _, label = self._running
        future, self._future = self._future, None
        self._running = None
        try:
            pixels = future.result()
        except Exception as error:
            if key == self._key:
                self.canvas.clear_patch_preview()
                self.canvas.patch_preview_status = f"{label} · 미리보기 실패: {error}"
                self.canvas.update()
        else:
            if key == self._key:
                self.canvas.set_patch_preview(bgr_to_qpixmap(pixels), patch.x_pos, patch.y_pos)
                self.canvas.patch_preview_status = f"{label} · 최종 합성 미리보기"
                self.canvas.update()
        self._start_pending()
        if self._future is None:
            self._timer.stop()
