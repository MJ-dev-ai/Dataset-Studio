from __future__ import annotations

from pathlib import Path


# Application and runtime paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSET_ROOT = PROJECT_ROOT / "assets"
RUNTIME_LOG_DIRECTORY = PROJECT_ROOT / "runtime" / "logs"

APP_NAME = "Dataset Editor"
DEFAULT_THEME = "light"
WORKER_SHUTDOWN_TIMEOUT_MS = 30_000

LOGGER_NAME = "dataset_editor"
LOG_FILE_MAX_BYTES = 10 * 1024 * 1024
LOG_BACKUP_COUNT = 5


# Image, history, and cache limits
_MIB = 1024 * 1024

HISTORY_MEMORY_BUDGET_BYTES = 256 * _MIB
HISTORY_MAX_STATES = 50
PIXMAP_CACHE_BUDGET_BYTES = 384 * _MIB
AUGMENTATION_CACHE_BUDGET_BYTES = 512 * _MIB

CANVAS_MIN_ZOOM = 0.02
CANVAS_MAX_ZOOM = 64.0
SELECTION_HANDLE_SIZE = 8


# Main-window layout defaults
LOG_CONSOLE_MAX_BLOCKS = 500
PANEL_LAYOUT_DELAY_MS = 0

LEFT_TOOLS_WIDTH_RATIO = 0.035
LEFT_PROJECT_WIDTH_RATIO = 0.14
RIGHT_PROPERTIES_WIDTH_RATIO = 0.17
BOTTOM_LOGS_HEIGHT_RATIO = 0.15
TOP_OPTIONS_HEIGHT_RATIO = 0.045


# Dataset and augmentation presets
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")
IMAGE_DIALOG_FILTER = f"Images ({' '.join(f'*{extension}' for extension in IMAGE_EXTENSIONS)});;All Files (*)"
MAP_SPECS = (
    ("albedo.png", "albedo_map"),
    ("albedo_map.png", "albedo_map"),
    ("normal_map.png", "normal_map"),
    ("best_curvature_map.png", "curvature_map"),
    ("curvature_map.png", "curvature_map"),
)

AUTOAUGMENT_GENERATE_SAMPLES = 300
AUTOAUGMENT_MAX_SAME_CLASS_PER_IMAGE = 1
AUTOAUGMENT_RANDOM_MULTIPLIER = 1
AUTOAUGMENT_ROTATION_ANGLES = (45, 90, 135, 180, 225, 270, 315)
AUTOAUGMENT_TRAIN_PERCENT = 80
AUTOAUGMENT_VALIDATION_PERCENT = 10
AUTOAUGMENT_TEST_PERCENT = 10
