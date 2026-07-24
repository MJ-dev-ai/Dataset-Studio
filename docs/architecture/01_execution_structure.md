# Dataset Studio Execution Structure

이 문서는 1차 구조 정리 기준이다. 목표는 UI, App, Worker, Service의 책임을 고정해서 `ui/mainwindow.py`가 앱 전체를 직접 관리하는 상태를 줄이는 것이다.

## Core Rule

```text
ui -> app -> worker -> service -> core/config
```

- `ui`: 화면, 위젯, 다이얼로그, 사용자 입력, signal emit만 담당한다.
- `app`: UI signal을 받아 작업을 선택하고, worker 생명주기와 service 호출 흐름을 관리한다.
- `worker`: QThread에서만 동작하는 긴 작업 wrapper다. 모든 service에 worker가 필요한 것은 아니다.
- `service`: 동기/비동기와 무관한 기능 API다. UI를 모르고, 필요하면 worker가 감싸서 호출한다.
- `core`: MapSet, project, image IO, geometry, logging처럼 앱 전역 도메인/기반 기능이다.
- `config`: 기본값과 설정값만 둔다.

## Target Tree

```text
dataset_studio/
├─ main.py
├─ app.py
├─ requirements.txt
├─ CHANGELOG.md
├─ config/
│  ├─ __init__.py
│  └─ default_presets.py
├─ core/
│  ├─ __init__.py
│  ├─ bbox.py
│  ├─ geometry.py
│  ├─ image_io.py
│  ├─ logging_setup.py
│  ├─ mapset.py
│  ├─ mask_ops.py
│  ├─ project.py
│  └─ qt_image.py
├─ service/
│  ├─ __init__.py
│  ├─ augmentation_service.py
│  ├─ editing_service.py
│  ├─ labeling_service.py
│  ├─ preprocessing_service.py
│  ├─ project_service.py
│  ├─ roi_service.py
│  ├─ tool_service.py
│  └─ yolo_export_service.py
├─ worker/
│  ├─ __init__.py
│  ├─ base_worker.py
│  ├─ augmentation_worker.py
│  ├─ editing_worker.py
│  ├─ project_worker.py
│  ├─ yolo_export_worker.py
│  └─ poisson_worker.py
├─ ui/
│  ├─ __init__.py
│  ├─ augmentation_dialog.py
│  ├─ export_dialog.py
│  ├─ imagecanvas.py
│  ├─ label_add_dialog.py
│  ├─ label_manager_dialog.py
│  ├─ mainwindow.py
│  ├─ mainwindow.ui
│  ├─ map_selection_dialog.py
│  ├─ mapset_selection_dialog.py
│  ├─ patch_clipboard_widget.py
│  ├─ preprocess_dialog.py
│  ├─ themes.py
│  ├─ uisetup.py
│  └─ autoaugment.ui
├─ tools/
│  ├─ __init__.py
│  ├─ label_tools.py
│  ├─ navigation_tools.py
│  ├─ paint_tools.py
│  ├─ patch_tools.py
│  ├─ selection_tools.py
│  └─ tool_mode.py
├─ assets/
│  └─ icons/
├─ training/
│  ├─ __init__.py
│  ├─ README.md
│  ├─ config/
│  │  ├─ __init__.py
│  │  └─ yolo_train_config.py
│  ├─ datasets/
│  │  └─ README.md
│  ├─ notebooks/
│  │  ├─ yolov8_custom_training_pipeline_albedo_map.ipynb
│  │  ├─ yolov8_tiny_defect_tiling_pipeline.ipynb
│  │  └─ yolov8n_2048_train_pipeline.ipynb
│  ├─ scripts/
│  │  ├─ visualize_result_test.py
│  │  └─ yolo_dataset_tools.py
│  ├─ weights/
│  │  ├─ yolo26n.pt
│  │  └─ yolov8n.pt
│  └─ workspace/
│     ├─ normal_validate/
│     ├─ period_saves_curv/
│     └─ runs_detect/
├─ runtime/
│  ├─ logs/
│  │  ├─ crash.log
│  │  ├─ dataset_studio.log
│  │  └─ pending_crash.log
│  ├─ outputs/
│  └─ cache/
├─ docs/
│  ├─ README.md
│  └─ architecture/
│     └─ 01_execution_structure.md
└─ scripts/
   └─ README.md
```

`service/`와 `worker/`는 1:1 관계가 아니다. Worker는 사용자 입장에서 하나의 긴 기능 단위만 대표한다. 예를 들어 orientation augmentation은 별도 worker를 만들지 않고 `augmentation_worker.py`에서 처리한다. 단일 이미지 변환 preview는 `preprocessing_service`를 UI/App에서 즉시 호출할 수 있고, 전체 MapSet batch preprocessing처럼 오래 걸리는 작업만 worker로 감싼다.

## Current Findings

현재 `ui/mainwindow.py`가 다음 책임을 모두 가지고 있다.

- project/mapset scan, manifest read/write
- QThread task start/cancel/shutdown
- save/export/import worker task 구성
- label catalog와 YOLO label load/save
- patch clipboard와 manual poisson 실행
- preprocessing 실행
- augmentation page 연결
- UI 패널과 상태 표시

따라서 `MainWindow`는 앞으로 view/controller 역할만 남기고, 앱 조립과 작업 실행은 `app.py`로 이동해야 한다.

중복 파일도 있다.

- `core/taskmanager.py` == `workers/taskmanager.py`
- `core/yolo_export.py` == `export/yoloexportapi.py`
- `core/defect_export.py` == `augmentation/defect_export.py`

중복의 canonical 위치는 아래 매핑을 따른다.

## Source Mapping

| Current file | Target | Decision |
| --- | --- | --- |
| `main.py` | `main.py` | 유지. QApplication 생성, logging, fatal shutdown hook만 둔다. |
| `app.py` | `app.py` | 확장. TIPS의 `core/app.py`처럼 MainWindow, worker, QThread 생명주기, task id/result routing을 한 곳에서 관리한다. Service/API registry는 app에 두지 않는다. |
| `ui/mainwindow.py` | `ui/mainwindow.py` | 축소. 화면 상태, widget signal emit, display update만 남긴다. 작업 실행 로직은 app/worker/service로 이동한다. |
| `ui/uisetup.py` | `ui/uisetup.py` | 유지. 버튼/action 연결은 UI signal emit 방식으로 바꾼다. |
| `ui/imagecanvas.py` | `ui/imagecanvas.py` | 유지. canvas rendering/input surface. 도메인 작업은 service로 이동한다. |
| `ui/*dialog.py` | `ui/` | 유지. 옵션 수집만 담당한다. |
| `ui/augmentationpage.py` | `ui/augmentationpage.py` | 유지하되 API 직접 호출 제거. run/cancel 요청 signal만 emit한다. |
| `core/mapset.py` | `core/mapset.py` | 유지. MapSet 도메인 모델과 discovery helper. |
| `core/project.py` | `core/project.py` | 유지/확장. DatasetProject 상태와 manifest model을 둔다. |
| `core/image_io.py` | `core/image_io.py` | 유지. 낮은 수준 이미지 IO. |
| `core/mask_ops.py` | `core/mask_ops.py` | 유지. 공통 mask primitive. |
| `core/geometry.py` | `core/geometry.py` | 유지. 공통 geometry primitive. |
| `core/qt_image.py` | `core/qt_image.py` | 유지. Qt 이미지 변환 유틸. |
| `core/logging_setup.py` | `core/logging_setup.py` | 유지. |
| `core/pixmap_cache.py` | `ui/pixmap_cache.py` or `core/pixmap_cache.py` | UI 캐시 성격. 당장은 유지, 나중에 UI 계층으로 이동 가능. |
| `core/taskmanager.py` | `app.py` | 통합. QThread 소유자는 worker가 아니라 app orchestration 계층이다. |
| `workers/taskmanager.py` | remove | `core/taskmanager.py`와 동일한 중복. `app.py`로 통합 후 제거. |
| `workers/baseworker.py` | `worker/base_worker.py` | 유지/이동. 단순 QThread 함수 worker는 가능하면 TaskManager 기반으로 통합한다. |
| `workers/augmentationworker.py` | `worker/augmentation_worker.py` | augmentation 계열 긴 작업의 대표 worker. auto/orientation/preview batch를 여기서 처리한다. |
| `core/mapset_export.py` | `service/project_service.py` | 이동. MapSet 저장/갱신 transaction은 project 기능에 포함한다. 긴 저장 작업은 `project_worker.py`가 호출한다. |
| `core/yolo_export.py` | `service/yolo_export_service.py` | 이동. canonical. |
| `export/yoloexportapi.py` | remove | `core/yolo_export.py`와 동일한 중복. |
| `core/defect_export.py` | `service/project_service.py` | 이동. defect export/import는 project/mapset 산출물 기능으로 통합한다. |
| `augmentation/defect_export.py` | remove | `core/defect_export.py`와 동일한 중복. |
| `core/patch_clipboard.py` | `service/editing_service.py` or `core/patch_clipboard.py` | copy/paste 편집 기능과 묶는다. 2차 MapSet 단위 정리 전까지는 core 유지 가능. |
| `augmentation/augmentationapi.py` | `service/augmentation_service.py` | 이동. 이미지 단위 예외 작업을 포함한 augmentation API. 긴 작업은 worker가 호출한다. |
| `augmentation/roi_ops.py` | `service/roi_service.py` | ROI contour 검출/정규화/참조 이미지 생성은 기능 API이므로 service에 둔다. |
| `augmentation/placement_ops.py` | `service/augmentation_service.py` helper | augmentation 내부 helper로 유지하거나 service 하위로 이동. |
| `augmentation/orientation_ops.py` | `service/augmentation_service.py` helper | augmentation 내부 helper로 유지하거나 service 하위로 이동. |
| `editing/poissonapi.py` | `service/editing_service.py` | 이동. Poisson/hard paste 기능 API. manual poisson이 길면 `poisson_worker`가 호출한다. |
| `editing/patch_ops.py` | `service/editing_service.py` helper | patch transform/mask helper. |
| `preprocessing/preprocessapi.py` | `service/preprocessing_service.py` | 이동. 단일 preview는 동기 호출 가능, batch는 worker 사용. |
| `preprocessing/image_ops.py` | `service/preprocessing_service.py` helper | preprocessing 내부 helper. |
| `labeling/yoloapi.py` | `service/labeling_service.py` | 이동. YOLO label load/save/auto label API. |
| `labeling/bbox_ops.py` | `core/bbox.py` or `service/labeling_service.py` helper | bbox primitive. core 후보. |
| `labeling/catalog.py` | `service/labeling_service.py` | label catalog update/remove/move service. |
| `tools/toolmanager.py` | `service/tool_service.py` | Tool mode registration/activation/cancel orchestration은 service로 이관한다. 기존 파일은 호환 wrapper로만 남긴다. |
| `tools/*` | `tools/` | concrete tool event handlers만 남긴다. ToolMode state machine은 `service/tool_service.py`에서 관리한다. |
| `config/default_presets.py` | `config/default_presets.py` | 유지. |
| `README.md` | `docs/README.md` | 사용자/개발 문서는 docs 아래로 모은다. |
| `config/yolo_train_config.py` | `training/config/yolo_train_config.py` | 앱 런타임 설정이 아니라 YOLO 학습 설정이다. training으로 분리한 뒤 앱 리팩토링 범위에서 제외한다. |
| `utils/yolo_dataset_tools.py` | `training/scripts/yolo_dataset_tools.py` | YOLO dataset 생성/분석/시각화 도구. training으로 분리한 뒤 앱 리팩토링 범위에서 제외한다. |
| `visualize_result_test.py` | `training/scripts/visualize_result_test.py` | YOLO 결과 시각화/검증 스크립트. training으로 분리한 뒤 앱 리팩토링 범위에서 제외한다. |
| `yolov8_custom_training_pipeline_albedo_map.ipynb` | `training/notebooks/yolov8_custom_training_pipeline_albedo_map.ipynb` | 학습/실험 노트북. |
| `yolov8_tiny_defect_tiling_pipeline.ipynb` | `training/notebooks/yolov8_tiny_defect_tiling_pipeline.ipynb` | 학습/실험 노트북. |
| `yolov8n_2048_train_pipeline.ipynb` | `training/notebooks/yolov8n_2048_train_pipeline.ipynb` | 학습/실험 노트북. |
| `yolo26n.pt` | `training/weights/yolo26n.pt` | 학습/추론 실험 weight. 앱 번들 모델이 되면 별도 `models/`로 승격. |
| `yolov8n.pt` | `training/weights/yolov8n.pt` | 학습/추론 실험 weight. 앱 번들 모델이 되면 별도 `models/`로 승격. |
| `yolo_workspace/` | `training/workspace/` | YOLO 학습 run, validation, checkpoint 산출물. 앱 런타임 루트에서 제거. |
| `assets/icons/resources_rc.py` | generated asset | 생성 파일. 구조 판단 대상에서 제외. |

## Out Of Scope After Migration

`training/`은 한 번 이동이 끝나면 앱 구조 정리와 런타임 리팩토링 범위에서 제외한다. 이후 작업에서는 `training/` 안의 파일을 읽거나 수정하지 않는다. 예외는 사용자가 명시적으로 YOLO 학습/실험 폴더를 다루라고 요청하는 경우뿐이다.

## Worker Boundary

Worker가 필요한 작업과 대표 worker:

- `project_worker.py`: dataset folder scan, project open/load, save current MapSet, save as new MapSet, defect pool import, defect export
- `augmentation_worker.py`: auto augmentation, orientation augmentation, augmentation preview/batch generation
- `editing_worker.py`: batch preprocessing or other long editing/preprocessing tasks
- `poisson_worker.py`: manual poisson apply across MapSet maps
- `yolo_export_worker.py`: YOLO dataset export and validation

Worker가 필수는 아닌 service:

- single image preview transform
- label catalog update
- bbox parse/format
- current canvas image conversion
- small ROI calculation for current image
- validation helpers

Worker 파일은 기능 대표 단위보다 더 잘게 나누지 않는다. 작업 내부 세부 모드는 enum/string command/dataclass request로 구분하고, worker는 progress/cancel/succeeded/failed만 emit한다. 어떤 worker를 실행하고 결과를 UI에 어떻게 연결할지는 app이 관리한다.

## App Responsibilities

`app.py`는 다음 객체를 소유해야 한다.

- `App`: TIPS의 `core/app.py`처럼 window와 thread orchestration을 묶는 QObject
- worker instances and QThread instances
- task id와 result handler registry
- UI signal wiring
- shutdown orchestration

`MainWindow`는 `TaskManager`를 직접 소유하지 않는다. 대신 `request_dataset_scan`, `request_mapset_save`, `request_yolo_export`, `request_auto_augmentation` 같은 signal을 emit하고, App이 실행한다.

`TaskManager`는 worker가 아니다. worker는 thread 안에서 실행되는 작업 객체이고, `TaskManager`는 app이 worker들을 생성/소유/종료하는 orchestration 객체다. 별도 파일로 분리하지 않고 `app.py` 내부 클래스 또는 `App`의 private 메서드로 둔다.

## Service Ownership Rule

App은 service/API를 전역 registry처럼 관리하지 않는다. App은 worker와 thread를 만들고 signal을 연결하는 역할에 집중한다.

- 긴 작업 service/API는 해당 worker가 소유한다.
- App은 필요하면 worker 생성자에 설정값이나 lightweight dependency만 전달한다.
- worker는 자기 기능에 필요한 service를 생성하거나 주입받고, run method 안에서 service를 호출한다.
- worker는 progress/cancel/succeeded/failed만 emit한다.
- UI에서 즉시 끝나는 작은 기능은 worker 없이 service를 호출할 수 있다. 이 경우에도 service는 UI 상태를 직접 모르고, 호출자는 결과만 받아 화면에 반영한다.

예:

```text
App
├─ ProjectWorker(project_service)
├─ AugmentationWorker(augmentation_service)
├─ EditingWorker(editing_service, preprocessing_service)
├─ PoissonWorker(editing_service)
└─ YoloExportWorker(yolo_export_service)
```

이 구조에서는 `AppContext`가 필수 객체가 아니다. 필요하다면 worker factory 정도로만 쓰고, service/API 소유권은 각 worker에 둔다.

## Service Consolidation Rule

Service도 worker와 같은 방식으로 사용자 기능 대표 단위만 남긴다.

- `project_service.py`: project open/manifest/mapset discovery/mapset save/defect import/export를 포함한다.
- `augmentation_service.py`: auto augmentation, orientation augmentation, augmentation preview와 placement/orientation helper를 포함한다.
- `editing_service.py`: patch copy/paste, poisson composition helper, clipboard model helper를 포함한다.
- `preprocessing_service.py`: resize/rotate/brightness/threshold/morphology 등 preprocessing 기능을 포함한다.
- `labeling_service.py`: YOLO label load/save, bbox 변환, label catalog 관리를 포함한다.
- `roi_service.py`: ROI contour 검출/정규화/참조 이미지 생성을 포함한다.
- `tool_service.py`: tool registration, mode activation, cancel/complete transition을 포함한다.
- `yolo_export_service.py`: YOLO dataset export, split, validation, data.yaml 생성을 포함한다.

`clipboard_service.py`, `defect_export_service.py`, `mapset_save_service.py`, `orientation_augmentation_worker.py`처럼 너무 세부적인 파일은 만들지 않는다. 필요한 구현은 대표 service/worker 내부 함수나 작은 private helper로 둔다.

## First Migration Order

1. `app.py`를 canonical app orchestration 모듈로 정하고 `core.taskmanager` / `workers.taskmanager` import를 치환한다.
2. `service/` 패키지를 만들고 대표 기능 service로 통합한다.
3. `app.py`에 `TaskManager` 소유권과 task result routing을 둔다.
4. `ui/mainwindow.py`에서 worker start/cancel/shutdown 로직을 제거하고 signal emit으로 바꾼다.
5. 중복 파일과 루트 실험 스크립트를 제거 또는 `scripts/`로 이동한다.

## Import Direction Guard

허용:

```text
ui -> core/config
ui -> app signal types only
app -> ui/worker/service/core/config
worker -> service/core/config
service -> core/config
tools -> ui canvas interfaces, core primitives
```

금지:

```text
service -> ui
service -> worker
core -> ui
core -> worker
worker -> ui widgets
```

Qt 타입이 필요한 기능은 `ui` 또는 `worker` 경계에 머문다. service는 가능하면 `Path`, `numpy.ndarray`, dataclass 같은 일반 타입으로 입출력한다.
