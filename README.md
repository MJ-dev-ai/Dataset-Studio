# Dataset Studio

Dataset Studio is a PySide6 desktop tool for building computer vision datasets from image and MapSet-based projects.

It is designed for workflows where editing, selection, labeling, preprocessing, synthetic defect/object insertion, and YOLO dataset export need to stay in one GUI instead of being split across small scripts.

The current project focus is dataset authoring and export. YOLO model training code is kept outside the runtime app under `training/`.

## Features

- Open image folders and MapSet-style datasets
- View, zoom, pan, and switch between related map images
- Rectangle, polygon, lasso, brush, eraser, fill, and bbox tools
- Patch clipboard with manual placement, transform, and Poisson blending
- Healing brush and selection-based editing for MapSet images
- Label class management and YOLO `.txt` label load/save
- Preprocessing preview and apply flow for image transforms
- Auto augmentation workflow for patch/defect insertion
- YOLO dataset export with split and `data.yaml` generation
- Background workers for long-running tasks with progress, cancel, and result signals

## Architecture

The app follows a UI -> App -> Worker -> Service ownership flow.

```text
ui/
  MainWindow, dialogs, canvas, visible state, user input, file dialogs

tools/
  ToolManager and pure tool state for canvas interaction

app.py
  Thread creation, signal/slot wiring, worker lifetime

worker/
  One execution sequence per feature, progress/result/error emission

service/
  Stateless calculation and data-processing functions

core/
  Project models, geometry, image IO, MapSet data, Qt image conversion
```

Important direction rules:

- UI owns visible state and emits requests downward.
- App owns `QThread` creation and worker signal wiring.
- Workers show the feature sequence directly and call services in order.
- Services are module-level function libraries, not stateful runtime objects.
- Results and progress move upward through Qt signals.

## Project Layout

```text
Dataset_Studio_UX/
├─ main.py
├─ app.py
├─ requirements.txt
├─ config/
├─ core/
├─ service/
├─ tools/
├─ ui/
├─ worker/
├─ assets/
├─ docs/
└─ training/
```

`training/` is intentionally separated from the app runtime. Use it only for training notebooks, model experiments, or training-specific dependencies.

## Requirements

Recommended environment:

```text
OS: Windows 10/11
Python: 3.11
GUI: PySide6
```

Install dependencies:

```powershell
py -3.11 -m venv .pyenv
.\.pyenv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

If PowerShell blocks activation in the current session:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.pyenv\Scripts\Activate.ps1
```

## Run

Run from the repository root:

```powershell
python main.py
```

If `PySide6` is missing, reinstall the GUI dependency:

```powershell
python -m pip install PySide6
```

## Dataset Notes

Dataset Studio can work with ordinary images and MapSet-like folders where one sample has multiple related maps, such as:

```text
sample_001/
├─ albedo_map.png
├─ normal_map.png
├─ curvature_map.png
└─ label.txt
```

The exact map keys are configured in `config/settings.py`.

## YOLO Export

The runtime app supports exporting the current dataset and labels into YOLO-style structures.

Typical output:

```text
yolo_dataset/
├─ images/
│  ├─ train/
│  ├─ val/
│  └─ test/
├─ labels/
│  ├─ train/
│  ├─ val/
│  └─ test/
└─ data.yaml
```

Training itself is not part of the GUI runtime.

## Development Notes

- Follow Python naming rules: `PascalCase` classes, `snake_case` functions and variables, `UPPER_CASE` constants.
- Keep internal helpers private with a leading underscore.
- Prefer direct, readable feature flow over empty wrappers.
- Keep heavy work out of the GUI thread.
- Keep services stateless and callable without constructing service objects.

## Documentation

- [docs/README.md](docs/README.md)
- [docs/architecture/01_execution_structure.md](docs/architecture/01_execution_structure.md)
- [CHANGELOG.md](CHANGELOG.md)

## Status

Dataset Studio is under active development. The current focus is stabilizing the PySide6 GUI, MapSet editing flow, worker/service boundaries, and YOLO dataset export.
