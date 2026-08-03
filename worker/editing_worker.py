from __future__ import annotations

from service.editing_service import PoissonApi, apply_healing_to_images
from worker.base_worker import BaseWorker


class EditingWorker(BaseWorker):
    """Run MapSet-wide healing and manual patch composition operations."""

    OPERATIONS = frozenset({"healing", "manual_poisson"})

    def __init__(self, task_id: str, operation: str, payload: object, poisson_api: PoissonApi, parent=None):
        super().__init__(task_id, operation, payload, parent)
        self.poisson_api = poisson_api

    def execute(self):
        if self.operation == "healing":
            return self._heal()
        if self.operation == "manual_poisson":
            return self._compose_manual_patch()
        raise ValueError(f"Unsupported editing operation: {self.operation}")

    def _heal(self):
        self.report(0, "Healing Brush started")

        def report(completed: int, total: int, key: str) -> None:
            self.report(
                round(completed / max(1, total) * 100),
                f"Healing Brush {completed}/{total}: {key}",
            )

        results = apply_healing_to_images(
            self.payload["images"],
            self.payload["strokes"],
            self.payload["size"],
            self.payload["opacity"],
            check_cancelled=self.check_cancelled,
            progress=report,
        )
        self.report(100, "Healing Brush complete")
        return results

    def _compose_manual_patch(self):
        payload = self.payload
        mode = payload["mode"]
        inputs = payload["composition_inputs"]
        results = {}
        total = len(inputs)
        for index, (map_key, values) in enumerate(inputs.items(), start=1):
            self.check_cancelled()
            target, patch, mask, x_pos, y_pos = values
            self.report(
                round((index - 1) / max(1, total) * 100),
                f"Applying Poisson to {map_key}",
            )
            if mode == "boundary_mixed":
                result = self.poisson_api.boundary_mixed_blend(target, patch, mask, x_pos, y_pos)
            elif mode == "hard_paste":
                result = self.poisson_api.hard_paste(target, patch, mask, x_pos, y_pos)
            elif mode is None:
                result = self.poisson_api.detail_preserve_blend(
                    target,
                    patch,
                    mask,
                    x_pos,
                    y_pos,
                    adapt_color="normal" not in map_key.casefold(),
                )
            else:
                result = self.poisson_api.compose_patch(
                    target, patch, mask, x_pos, y_pos, mode=mode, fallback=False
                )
            results[map_key] = result
        self.report(100, "Manual Poisson complete")
        return results

