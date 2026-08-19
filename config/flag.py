from __future__ import annotations

from dataclasses import dataclass


@dataclass
class UiFlag:
	is_loading_project: bool = False
	is_saving_project: bool = False
	is_editing_image: bool = False
	is_auto_augmenting: bool = False
	is_exporting_yolo: bool = False
	is_shutting_down: bool = False


@dataclass
class WorkerFlag:
	stop_requested: bool = False
	is_running: bool = False
