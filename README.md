# Dataset Studio

**Dataset Studio**는 Computer Vision 데이터셋 제작 과정을 하나의 GUI 안에서 처리하기 위해 만든 PySide6 기반 데스크톱 애플리케이션입니다.

이미지 확인, MapSet 관리, 선택 영역 편집, 라벨링, Poisson 기반 합성, 전처리, 자동 증강, YOLO 데이터셋 export까지 데이터 제작 과정에서 반복되는 작업을 한 흐름으로 묶는 것을 목표로 합니다.

## 프로젝트 주요 사항

- PySide6 기반 Dataset Authoring GUI 구현
- 이미지 단일 파일과 다중 MapSet 폴더를 함께 다루는 프로젝트 구조 구현
- Canvas 중심의 zoom, pan, map switching, selection, annotation overlay 구현
- Rectangle, Polygon, Lasso, Brush, Eraser, Fill, BBox, Patch 도구 구현
- ToolManager가 mouse event와 image 좌표 변환을 소유하도록 도구 구조 정리
- YOLO `.txt` 라벨 로드, 저장, 클래스 관리, bbox 생성 기능 구현
- 선택 영역 기반 patch clipboard와 MapSet 단위 patch copy/paste 구현
- Manual Poisson, Boundary Mixed, Hard Paste 등 합성 흐름 구현
- Healing Brush, selection fill/delete, MapSet 단위 undo/redo 구현
- 전처리 preview/apply 흐름과 annotation affine transform 반영
- AutoAugment UI, class balance 표시, preview, batch generation 흐름 구현
- YOLO dataset export, split, `data.yaml` 생성 흐름 구현
- 긴 작업을 GUI thread에서 분리하기 위한 App/Worker/Service 구조 리팩토링
- YOLO 학습 관련 코드는 runtime 범위에서 제외하고 `training/`으로 분리

## 주요 기능

### Project & MapSet Management

Dataset Studio는 일반 이미지뿐 아니라 하나의 샘플이 여러 map 이미지로 구성된 MapSet 프로젝트를 다룰 수 있습니다.

예시:

```text
sample_001/
├─ albedo_map.png
├─ normal_map.png
├─ curvature_map.png
└─ label.txt
```

지원 기능:

- Dataset folder scan
- Project open/save
- Project explorer tree
- Map tab switching
- MapSet save/save as/save all
- MapSet 단위 변경 이력 관리
- 현재 map과 관련 label 상태 캐싱

### Canvas & Tools

Canvas는 데이터 제작 작업의 중심입니다. 이미지를 단순히 보여주는 뷰어가 아니라, selection, editing, labeling, patch placement가 모두 같은 좌표계에서 동작하도록 구성했습니다.

구현된 도구:

- Move/Pan
- Rectangle Selection
- Polygon Selection
- Lasso Selection
- Brush
- Eraser
- Fill
- Healing Brush
- Patch Placement
- BBox Label Tool

도구 입력 흐름은 `ImageCanvas -> ToolManager -> tools` 구조로 정리했습니다. `ToolManager`가 mouse event, wheel event, drop event, image 좌표 변환을 담당하고, 개별 tool 파일은 선택/브러시/패치 상태 계산에 집중합니다.

### Labeling

YOLO 객체 검출 데이터셋 제작을 위한 라벨링 기능을 포함합니다.

지원 기능:

- BBox 생성
- 선택 영역 기반 label 생성
- Label Class Manager
- Class ID와 class name 관리
- YOLO `.txt` load/save
- 기존 label overlay 표시
- annotation 선택, 삭제, 저장 상태 추적
- preprocessing 적용 시 bbox 좌표 transform 반영

### Patch Clipboard & Poisson Editing

선택 영역을 patch로 복사하고, 다른 이미지 또는 같은 MapSet의 target map에 배치한 뒤 합성할 수 있습니다.

지원 기능:

- Selection to patch
- MapSet patch clipboard
- Patch drag placement
- Patch move/rotate/scale
- Preview와 실제 합성 좌표 동기화
- Manual Poisson
- Boundary Mixed blending
- Detail Preserve blending
- Hard Paste fallback
- MapSet 전체에 같은 placement 기준으로 합성 적용

이 기능은 결함 데이터 합성, 객체 삽입, 학습 데이터 보강에 사용할 수 있도록 설계했습니다.

### Image Editing

데이터 제작 과정에서 필요한 기본 편집 기능을 제공합니다.

지원 기능:

- Brush paint
- Eraser
- Selection fill
- Selection delete
- Healing Brush
- MapSet 단위 edit commit
- Undo/Redo
- 이미지 크기와 selection/mask 좌표계 검증

무거운 편집 작업은 worker를 통해 실행하고, 결과는 signal로 UI에 반영합니다.

### Preprocessing

학습 전 이미지 정리를 위한 전처리 UI와 적용 흐름을 제공합니다.

지원 기능:

- Resize
- Rotate
- Flip
- Brightness/Contrast
- CLAHE
- Sharpen
- Threshold
- Preview
- Current image / current MapSet / all MapSets 적용
- Annotation 좌표 affine transform 반영

### Auto Augmentation

부족한 class를 보강하기 위한 자동 증강 흐름을 별도 UI로 구성했습니다.

지원 기능:

- Defect/Patch pool 선택
- Target map 선택
- Class balance 표시
- 예상 output count 계산
- Split 비율 설정
- Poisson 기반 synthetic sample 생성
- Flip/rotation/random augmentation
- Preview sample 표시
- Progress, cancel, result summary
- 생성 결과 폴더 열기

### YOLO Dataset Export

현재 프로젝트의 이미지와 라벨을 YOLO 학습용 폴더 구조로 export할 수 있습니다.

출력 예시:

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

앱의 범위는 dataset export까지입니다. YOLO model training 관련 파일은 `training/` 폴더로 분리했습니다.

## 구조

```text
Dataset_Studio_UX/
├─ main.py
├─ app.py
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

역할:

- `ui/`: MainWindow, dialogs, canvas, visible state, file dialog
- `tools/`: ToolManager와 selection/paint/patch/bbox tool state
- `app.py`: QThread 생성, signal/slot 연결, worker lifetime 관리
- `worker/`: 기능별 실행 sequence와 progress/result/error signal
- `service/`: 객체 생성 없이 호출하는 stateless 연산 함수
- `core/`: project, mapset, geometry, image IO, Qt image 변환
- `config/`: settings, default presets, UI flag

## 설계 방향

이 프로젝트는 다음 흐름을 기준으로 리팩토링했습니다.

```text
UI -> App -> Worker -> Service
```

- UI는 화면 상태, 사용자 입력, file dialog, signal emit을 담당합니다.
- App은 worker thread 생성과 signal/slot 연결만 담당합니다.
- Worker는 기능 sequence를 직접 보여주고 service 함수를 순서대로 호출합니다.
- Service는 class 없이 함수와 상수 중심으로 구성합니다.
- 결과, progress, error는 signal을 통해 위로 올라옵니다.

## 설치

권장 환경:

```text
OS: Windows 10/11
Python: 3.11
GUI: PySide6
```

설치:

```powershell
py -3.11 -m venv .pyenv
.\.pyenv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

PowerShell에서 venv 활성화가 막히면 현재 세션에서만 실행 정책을 허용합니다.

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.pyenv\Scripts\Activate.ps1
```

## 실행

프로젝트 루트에서 실행합니다.

```powershell
python main.py
```

## 문서

- [docs/README.md](docs/README.md)

## 현재 상태

Dataset Studio는 개발 중인 데이터셋 제작 도구입니다. 현재는 PySide6 GUI 안정화, MapSet 편집 흐름, ToolManager 구조, Worker/Service 경계, YOLO export 흐름을 중심으로 정리하고 있습니다.
