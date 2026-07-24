import numpy as np

from worker.healing_worker import run_mapset_healing


class FakeTaskContext:
    def __init__(self):
        self.reports = []
        self.cancel_checks = 0

    def check_cancelled(self):
        self.cancel_checks += 1

    def report(self, value, message=""):
        self.reports.append((value, message))


def test_healing_worker_reports_progress_and_returns_results():
    image = np.full((50, 50, 3), 120, dtype=np.uint8)
    image[25, 18:34] = 20
    context = FakeTaskContext()

    results = run_mapset_healing(
        context,
        {"normal": image},
        [((10, 10), (10, 10), (26, 25), (26, 25))],
        size=14,
        opacity=1.0,
    )

    assert set(results) == {"normal"}
    assert context.reports[0] == (0, "Healing Brush started")
    assert context.reports[-1] == (100, "Healing Brush complete")
    assert context.cancel_checks > 0
