from __future__ import annotations

from PyQt6.QtCore import QMimeData, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QDrag, QIcon
from PyQt6.QtWidgets import QAbstractItemView, QListView, QListWidget, QListWidgetItem, QMenu

from core.patch_clipboard import PATCH_MIME_TYPE, PatchClipboard
from core.qt_image import bgr_mask_to_qpixmap


class PatchClipboardWidget(QListWidget):
    """Thumbnail view that exports stable patch IDs through Qt drag-and-drop."""

    clip_activated = pyqtSignal(str)
    clipboard_changed = pyqtSignal()
    import_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._clipboard: PatchClipboard | None = None
        self.setObjectName("listMasks")
        self.setIconSize(QSize(72, 72))
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Static)
        self.setWrapping(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.itemDoubleClicked.connect(self._emit_activated)

    def set_clipboard(self, clipboard: PatchClipboard) -> None:
        """Bind the owned clipboard model and rebuild thumbnails."""
        self._clipboard = clipboard
        self.refresh()

    def refresh(self, select_id: str | None = None) -> None:
        """Rebuild items while optionally restoring one stable selection."""
        self.clear()
        if self._clipboard is None:
            return
        for clip in self._clipboard.items():
            item = QListWidgetItem(clip.name)
            item.setData(Qt.ItemDataRole.UserRole, clip.clip_id)
            item.setToolTip(
                f"{clip.name}\n{clip.image.shape[1]} × {clip.image.shape[0]}"
                f"\nMaps: {', '.join(clip.map_keys)}"
                + (f"\n{clip.source_path}" if clip.source_path is not None else "")
            )
            item.setIcon(QIcon(bgr_mask_to_qpixmap(clip.image, clip.mask)))
            self.addItem(item)
            if clip.clip_id == select_id:
                self.setCurrentItem(item)

    def selected_clip_id(self) -> str | None:
        """Return the currently selected stable clip ID."""
        item = self.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole)) if item is not None else None

    def mimeTypes(self) -> list[str]:
        return [PATCH_MIME_TYPE]

    def mimeData(self, items: list[QListWidgetItem]) -> QMimeData:
        mime = QMimeData()
        if items:
            clip_id = str(items[0].data(Qt.ItemDataRole.UserRole))
            mime.setData(PATCH_MIME_TYPE, clip_id.encode("ascii"))
        return mime

    def startDrag(self, supported_actions) -> None:
        item = self.currentItem()
        if item is None:
            return
        drag = QDrag(self)
        drag.setMimeData(self.mimeData([item]))
        drag.setPixmap(item.icon().pixmap(self.iconSize()))
        drag.exec(Qt.DropAction.CopyAction)

    def _emit_activated(self, item: QListWidgetItem) -> None:
        self.clip_activated.emit(str(item.data(Qt.ItemDataRole.UserRole)))

    def _show_context_menu(self, position) -> None:
        if self._clipboard is None:
            return
        menu = QMenu(self)
        import_action = menu.addAction("Import Defect Pool...")
        menu.addSeparator()
        remove_action = menu.addAction("Remove Patch")
        clear_action = menu.addAction("Clear Clipboard")
        selected = menu.exec(self.mapToGlobal(position))
        if selected is import_action:
            self.import_requested.emit()
        elif selected is remove_action:
            clip_id = self.selected_clip_id()
            if clip_id and self._clipboard.remove(clip_id):
                self.refresh()
                self.clipboard_changed.emit()
        elif selected is clear_action:
            self._clipboard.clear()
            self.refresh()
            self.clipboard_changed.emit()
