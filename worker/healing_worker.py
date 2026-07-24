from __future__ import annotations

from typing import Protocol

import numpy as np

from service.editing_service import HealingStroke, apply_healing_to_images


class HealingTaskContext(Protocol):
    """TaskManager context surface used by the healing worker."""

    def check_cancelled(self) -> None:
        """Raise when the user cancelled this background task."""

    def report(self, value: int, message: str = "") -> None:
        """Emit task progress back to the app controller."""


def run_mapset_healing(
    context: HealingTaskContext,
    images: dict[str, np.ndarray],
    strokes: list[HealingStroke],
    size: int,
    opacity: float,
) -> dict[str, np.ndarray]:
    """Run MapSet-wide healing brush composition inside a TaskManager worker."""
    context.report(0, "Healing Brush started")

    def report(completed: int, total: int, key: str) -> None:
        percent = round(completed / max(1, total) * 100)
        context.report(percent, f"Healing Brush {completed}/{total}: {key}")

    results = apply_healing_to_images(
        images,
        strokes,
        size,
        opacity,
        check_cancelled=context.check_cancelled,
        progress=report,
    )
    context.report(100, "Healing Brush complete")
    return results
