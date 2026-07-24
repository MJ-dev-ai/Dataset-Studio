import time

from PyQt6.QtCore import QCoreApplication, QEventLoop, QTimer

from app import TaskManager


def _wait(manager, task_id, timeout_ms=2000):
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    manager.task_finished.connect(lambda value: loop.quit() if value == task_id else None)
    timer.start(timeout_ms)
    loop.exec()
    assert task_id not in manager.active_task_ids


def test_task_manager_releases_successful_thread():
    app = QCoreApplication.instance() or QCoreApplication([])
    manager = TaskManager()
    values = []
    manager.task_succeeded.connect(lambda _task_id, value: values.append(value))
    task_id = manager.start("success", lambda context: "done")
    _wait(manager, task_id)
    assert values == ["done"]
    assert app is not None


def test_shutdown_cooperatively_cancels_and_releases_threads():
    app = QCoreApplication.instance() or QCoreApplication([])
    manager = TaskManager()

    def work(context):
        while True:
            context.check_cancelled()
            time.sleep(0.005)

    task_id = manager.start("long", work)
    QTimer.singleShot(20, lambda: manager.cancel(task_id))
    _wait(manager, task_id)
    assert manager.shutdown(100)
    assert app is not None
