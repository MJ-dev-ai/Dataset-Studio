from __future__ import annotations

from PyQt6.QtCore import pyqtSignal

from worker.base_worker import BaseWorker


class AugmentationWorker(BaseWorker):
    """Worker reserved for augmentation preview and batch generation."""

    preview_ready = pyqtSignal(object)
    sample_finished = pyqtSignal(int, object)
