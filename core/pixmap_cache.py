from __future__ import annotations

import os
from collections import OrderedDict

from PyQt6.QtGui import QPixmap

from config.settings import PIXMAP_CACHE_BUDGET_BYTES


class PixmapCache:
    """Main-thread LRU cache for decoded map pixmaps with a fixed memory estimate budget."""

    def __init__(self, max_bytes: int = PIXMAP_CACHE_BUDGET_BYTES):
        self.max_bytes = max(0, max_bytes)
        self.size_bytes = 0
        self.hits = 0
        self.misses = 0
        self._items = OrderedDict()

    def load(self, path: str) -> QPixmap:
        normalized = os.path.normcase(os.path.normpath(path))
        try:
            stat = os.stat(path)
            key = (normalized, stat.st_mtime_ns, stat.st_size)
        except OSError:
            self.misses += 1
            return QPixmap()

        cached = self._items.get(key)
        if cached is not None:
            self._items.move_to_end(key)
            self.hits += 1
            return QPixmap(cached[0])

        self.misses += 1
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return pixmap
        estimated_bytes = pixmap.width() * pixmap.height() * 4
        self._remove_stale_path(normalized)
        self._items[key] = (QPixmap(pixmap), estimated_bytes)
        self.size_bytes += estimated_bytes
        self._evict()
        return pixmap

    def clear(self):
        self._items.clear()
        self.size_bytes = 0

    def _remove_stale_path(self, normalized_path: str):
        for key in [item_key for item_key in self._items if item_key[0] == normalized_path]:
            _pixmap, size = self._items.pop(key)
            self.size_bytes -= size

    def _evict(self):
        while self.size_bytes > self.max_bytes and self._items:
            _key, (_pixmap, size) = self._items.popitem(last=False)
            self.size_bytes -= size
