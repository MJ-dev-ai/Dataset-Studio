from __future__ import annotations

import sys
import threading
import traceback

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication

from app import DatasetEditorApp
from core.logging_setup import append_crash_report, append_pending_crash, configure_logging, flush_logs
from ui.themes import theme_stylesheet


class FatalShutdownController(QObject):
    """Move fatal shutdown work onto the GUI thread and flush crash diagnostics."""

    fatal = pyqtSignal(str)

    def __init__(self, app: QApplication, editor: DatasetEditorApp, logger):
        super().__init__()
        self.app = app
        self.editor = editor
        self.logger = logger
        self.fatal.connect(self._shutdown)

    def handle(self, exc_type, exc_value, exc_traceback) -> None:
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        self.logger.critical("Unhandled exception\n%s", text)
        append_pending_crash(text)
        append_crash_report("Unhandled exception", text)
        flush_logs(durable=True)
        self.fatal.emit(text)

    @pyqtSlot(str)
    def _shutdown(self, traceback_text: str) -> None:
        del traceback_text
        if self.editor.shutdown(timeout_ms=30000):
            flush_logs(durable=True)
            self.app.exit(1)
        else:
            self.logger.critical("Fatal shutdown is pending because workers did not stop")
            flush_logs(durable=True)


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(theme_stylesheet("dark"))
    logger = configure_logging("runtime/logs")
    editor = DatasetEditorApp(app, logger)
    controller = FatalShutdownController(app, editor, logger)
    sys.excepthook = controller.handle

    def thread_exception(args):
        controller.handle(args.exc_type, args.exc_value, args.exc_traceback)

    threading.excepthook = thread_exception
    editor.window.show()
    exit_code = app.exec()
    editor.shutdown(timeout_ms=30000)
    flush_logs(durable=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
