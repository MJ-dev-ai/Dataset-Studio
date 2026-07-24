# DatasetStudio

**DatasetStudio**는 이미지 기반 데이터셋을 제작하기 위한 통합 GUI 도구입니다.
이미지 편집, 라벨링, 전처리, Poisson 기반 합성, 자동 증강, YOLO 데이터셋 Export를 하나의 작업 흐름 안에서 수행하는 것을 목표로 합니다.

이 프로젝트는 특정 결함 데이터셋에만 한정되지 않고, 일반적인 Computer Vision 데이터셋 제작 작업에도 사용할 수 있도록 설계되었습니다.

---

## 주요 기능

### 1. Image Editing

DatasetStudio는 데이터셋 제작 과정에서 필요한 기본 이미지 편집 기능을 제공합니다.

지원 예정 기능:

* Brush
* Eraser
* Fill
* Blur / Smooth
* Threshold
* Morphology
* Patch Copy / Paste
* Poisson Editing

이미지를 단순히 확인하는 것이 아니라, 학습 데이터로 사용하기 전에 필요한 영역을 직접 수정하거나 보정할 수 있도록 구성됩니다.

---

### 2. Selection & Mask

이미지 편집, 결함 패치 생성, 라벨 자동 생성에 공통으로 사용되는 Selection / Mask 기능을 제공합니다.

지원 예정 기능:

* Rectangle Selection
* Polygon Selection
* Lasso Selection
* Brush Mask
* Eraser Mask
* Selection to Mask
* Mask to Bounding Box

선택 영역은 내부적으로 mask로 변환되며, Poisson 합성, patch export, labeling 기능에서 재사용됩니다.

---

### 3. Poisson Editing

선택한 이미지 영역을 다른 이미지에 자연스럽게 합성하기 위한 기능입니다.

주요 기능:

* Source 이미지에서 patch 선택
* Target 이미지에 patch preview
* Patch 이동 / 회전 / 크기 조정
* `cv2.seamlessClone` 기반 Poisson 합성
* 실패 시 hard paste fallback
* 합성 결과에 대한 label 자동 추가

이 기능은 결함 데이터 합성, 객체 삽입, 이미지 보강 등에 활용할 수 있습니다.

---

### 4. Labeling

YOLO 형식의 객체 검출 라벨을 생성하고 수정하는 기능입니다.

지원 예정 기능:

* Bounding Box 생성
* Bounding Box 이동 / 크기 조정
* Class 지정
* YOLO `.txt` 라벨 로드
* YOLO `.txt` 라벨 저장
* Mask 기반 Bounding Box 자동 생성
* Poisson 합성 결과 label 자동 추가

라벨은 이미지와 동일한 좌표계를 기준으로 관리됩니다.

---

### 5. Preprocessing

학습용 이미지 품질을 정리하기 위한 전처리 기능입니다.

지원 예정 기능:

* Resize
* Crop
* Padding
* Normalize
* CLAHE
* Blur
* Sharpen
* Threshold
* Morphology
* Map별 전처리 옵션

Photometric Stereo 결과물처럼 `albedo_map`, `normal_map`, `curvature_map`, `depth_map` 등 여러 map 이미지를 다루는 경우에도 map별 전처리를 적용할 수 있도록 설계됩니다.

---

### 6. Auto Augmentation

부족한 클래스나 특정 조건의 데이터를 자동으로 보강하기 위한 기능입니다.

지원 예정 기능:

* Class imbalance 분석
* 부족한 class 자동 선택
* Patch pool 기반 defect/object patch 선택
* Target 이미지 선택
* ROI 자동 검출
* ROI 내부 patch placement
* Poisson 기반 합성
* YOLO label 자동 append
* Preview sample 생성
* Batch augmentation 실행

Auto Augmentation 화면은 별도 UI로 구성되며, 실제 실행 전에 몇 가지 샘플 결과를 preview로 확인할 수 있도록 설계됩니다.

---

### 7. YOLO Dataset Export

작업한 이미지와 라벨을 YOLO 학습 구조로 내보내는 기능입니다.

지원 예정 기능:

* Train / Val / Test split
* Map별 dataset export
* `data.yaml` 생성
* 이미지 / 라벨 누락 검사
* YOLOv8 학습용 폴더 구조 생성

출력 예시:

```text
yolov8_dataset/
├─ albedo_map/
│  ├─ images/train/
│  ├─ images/val/
│  ├─ labels/train/
│  ├─ labels/val/
│  └─ data.yaml
│
├─ normal_map/
│  ├─ images/train/
│  ├─ images/val/
│  ├─ labels/train/
│  ├─ labels/val/
│  └─ data.yaml
│
└─ curvature_map/
   ├─ images/train/
   ├─ images/val/
   ├─ labels/train/
   ├─ labels/val/
   └─ data.yaml
```

---

## 프로젝트 구조

```text
dataset_studio/
├─ main.py
├─ app.py
├─ config/
│  ├─ __init__.py
│  └─ default_presets.py
├─ core/
│  ├─ geometry.py
│  ├─ image_io.py
│  ├─ logging_setup.py
│  ├─ mapset.py
│  ├─ mask_ops.py
│  ├─ patch_clipboard.py
│  ├─ pixmap_cache.py
│  ├─ project.py
│  └─ qt_image.py
├─ service/
│  ├─ augmentation_service.py
│  ├─ editing_service.py
│  ├─ labeling_service.py
│  ├─ preprocessing_service.py
│  ├─ project_service.py
│  ├─ roi_service.py
│  ├─ tool_service.py
│  └─ yolo_export_service.py
├─ worker/
│  ├─ base_worker.py
│  └─ augmentation_worker.py
├─ ui/
│  ├─ augmentationpage.py
│  ├─ exportdialog.py
│  ├─ imagecanvas.py
│  ├─ mainwindow.py
│  ├─ mainwindow.ui
│  ├─ preprocess_dialog.py
│  ├─ themes.py
│  └─ uisetup.py
├─ tools/
│  ├─ label_tools.py
│  ├─ navigation_tools.py
│  ├─ paint_tools.py
│  ├─ patch_tools.py
│  └─ selection_tools.py
├─ assets/
│  └─ icons/
├─ training/
│  ├─ config/
│  ├─ notebooks/
│  ├─ scripts/
│  ├─ weights/
│  └─ workspace/
├─ runtime/logs/
│  └─ .gitkeep
└─ runtime/outputs/results/
   └─ .gitkeep
```

---

## 설계 방향

DatasetStudio는 UI 코드와 알고리즘 코드를 분리하는 방식으로 설계됩니다.

### UI Layer

`ui/`는 사용자 입력, 화면 표시, 버튼 연결을 담당합니다. `tools/`는 실제 canvas tool 객체를 담고, `service/tool_service.py`의 `ToolMode`와 `ToolManager`가 해당 객체들을 현재 모드 기준으로 등록/전환/이벤트 dispatch합니다.

* `mainwindow.py`: 전체 창과 주요 모듈 조립
* `uisetup.py`: 메뉴, 툴바, 패널, 아이콘 설정
* `imagecanvas.py`: 이미지 표시, zoom, pan, overlay
* `augmentationpage.py`: Auto Augmentation 전용 화면
* `exportdialog.py`: Dataset Export 팝업

### Service Layer

`service/`는 UI와 분리된 기능 API를 제공합니다. 편집, 라벨링, 전처리, augmentation, ROI, project 저장/export, YOLO dataset export가 대표 service 단위로 통합되어 있습니다.

UI에서는 각 기능을 직접 구현하지 않고, connect 함수에서 필요한 API를 호출하는 방식으로 개발합니다.

예시:

```python
self.poisson_api.poisson_blend(...)
self.yolo_api.save_labels(...)
self.preprocess_api.apply_clahe(...)
self.augmentation_api.create_preview_samples(...)
self.yolo_export_api.export_dataset(...)
```

---

## 개발 환경

권장 환경:

```text
OS: Windows 10/11
Python: 3.11
GUI: PyQt6
Deep Learning: PyTorch CUDA 11.8
```

가상환경 생성:

```powershell
py -3.11 -m venv .pyenv
```

가상환경 활성화:

```powershell
.\.pyenv\Scripts\Activate.ps1
```

PowerShell 실행 정책 오류가 발생하면 현재 세션에서만 허용합니다.

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.pyenv\Scripts\Activate.ps1
```

패키지 설치:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

## CUDA 확인

PyTorch CUDA가 정상적으로 설치되었는지 확인합니다.

```powershell
python -c "import torch; print('torch:', torch.__version__); print('cuda:', torch.version.cuda); print('available:', torch.cuda.is_available()); print('device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
```

정상 예시:

```text
torch: 2.x.x+cu118
cuda: 11.8
available: True
device: NVIDIA ...
```

---

## 실행 방법

프로젝트 루트에서 실행합니다.

```powershell
python main.py
```

또는 패키지 실행 구조를 사용하는 경우:

```powershell
python -m dataset_studio.main
```

---

## Naming Convention

이 프로젝트는 Python 일반 규칙과 Google Python Style Guide를 기준으로 이름을 정합니다.

파일명:

```text
lowercase.py
```

클래스 파일명:

```text
MainWindow   → mainwindow.py
UiSetup      → uisetup.py
ImageCanvas  → imagecanvas.py
PoissonApi   → poissonapi.py
YoloApi      → yoloapi.py
BaseWorker   → baseworker.py
```

클래스명:

```python
class MainWindow:
    pass
```

함수명과 변수명:

```python
def load_project():
    pass

current_image = None
```

상수명:

```python
DEFAULT_IMAGE_SIZE = 640
```

---

## 변경 이력

버전별 구현 및 변경 사항은 [CHANGELOG.md](../CHANGELOG.md)를 참고하세요.

---

## 목표

DatasetStudio의 최종 목표는 Computer Vision 데이터셋 제작에 필요한 반복 작업을 하나의 GUI 안에서 처리하는 것입니다.

특히 다음 작업을 하나의 흐름으로 연결하는 것을 목표로 합니다.

```text
Dataset Load
→ Image Editing
→ Labeling
→ Preprocessing
→ Auto Augmentation
→ YOLO Dataset Export
→ Model Training
```

DatasetStudio는 단순한 이미지 뷰어가 아니라, 학습 데이터 제작을 위한 실용적인 Dataset Authoring Tool을 지향합니다.
