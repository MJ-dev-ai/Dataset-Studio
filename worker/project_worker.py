from __future__ import annotations

from core.mapset import discover_map_sets
from core.patch_clipboard import read_defect_pool
from service.project_service import export_defect_maps, save_mapset_copy, save_mapset_in_place
from worker.base_worker import BaseWorker


class ProjectWorker(BaseWorker):
    """Run dataset discovery, MapSet persistence, and defect file operations."""

    OPERATIONS = frozenset({
        "import_defect_pool",
        "scan_dataset",
        "save_mapset",
        "save_all",
        "save_mapset_copy",
        "export_defect",
    })

    def execute(self):
        handlers = {
            "import_defect_pool": self._import_defect_pool,
            "scan_dataset": self._scan_dataset,
            "save_mapset": self._save_mapset,
            "save_all": self._save_all,
            "save_mapset_copy": self._save_mapset_copy,
            "export_defect": self._export_defect,
        }
        try:
            return handlers[self.operation]()
        except KeyError as exc:
            raise ValueError(f"Unsupported project operation: {self.operation}") from exc

    def _import_defect_pool(self):
        self.report(0, "Reading Defect Pool")
        payloads = read_defect_pool(self.payload["root"])
        self.report(100, f"Loaded {len(payloads)} defects")
        return payloads

    def _scan_dataset(self):
        return discover_map_sets(
            root=self.payload["folder"],
            map_specs=self.payload["map_specs"],
            image_extensions=self.payload["image_extensions"],
            cancelled=lambda: self.is_cancelled,
            progress=lambda count, path: self.report(min(99, count), path),
        )

    def _save_mapset(self):
        save_mapset_in_place(
            self.payload["request"],
            cancelled=lambda: (self.check_cancelled() or False),
            progress=self._report_units,
        )
        return self.payload["label_path"]

    def _save_all(self):
        targets = self.payload["targets"]
        total_units = self.payload["total_units"]
        completed_units = 0
        saved: list[tuple[str, str]] = []
        for mapset, request in targets:
            self.check_cancelled()

            def report(completed: int, total: int, message: str) -> None:
                del total
                value = round((completed_units + completed) / max(1, total_units) * 100)
                self.report(value, f"{mapset.name}: {message}")

            save_mapset_in_place(
                request,
                cancelled=lambda: (self.check_cancelled() or False),
                progress=report,
            )
            completed_units += len(request.maps) + 1
            saved.append((str(mapset.folder.resolve()), str(request.label_path)))
        return saved

    def _save_mapset_copy(self):
        return save_mapset_copy(
            self.payload["request"],
            cancelled=lambda: (self.check_cancelled() or False),
            progress=self._report_units,
        )

    def _export_defect(self):
        payload = self.payload
        return export_defect_maps(
            payload["map_paths"],
            payload["output_root"],
            payload["defect_name"],
            payload["selection"],
            payload["bounds"],
            cancelled=lambda: self.is_cancelled,
            progress=lambda value, message: self.report(
                round(value / max(1, len(payload["map_paths"])) * 100), message
            ),
        )

    def _report_units(self, completed: int, total: int, message: str) -> None:
        self.report(round(completed / max(1, total) * 100), message)

