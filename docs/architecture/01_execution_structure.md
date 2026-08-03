# Dataset Editor 실행 구조

이 문서는 기능을 실행했을 때 실제 작업 위치와 의존 방향을 바로 추적하기 위한 기준이다.
파일 수를 늘리는 것보다 각 계층이 한 가지 책임을 갖는 것을 우선한다.

## 기본 흐름

```text
main.py
  -> app.DatasetEditorApp
       -> ui.MainWindow
       -> worker.ProjectWorker
       -> worker.EditingWorker
       -> worker.AugmentationWorker
       -> worker.ExportWorker
       -> service AppContext
```

- `main.py`: QApplication, theme, logging, fatal exception hook만 설정한다.
- `app.py`: 서비스를 조립하고 UI 신호를 기능별 worker로 연결한다. 활성 worker의 취소와 종료를 책임진다.
- `ui/`: 화면 상태, 사용자 입력, 캔버스 갱신, 가벼운 서비스 호출을 담당한다.
- `worker/`: QThread 생명주기와 무거운 서비스 호출을 기능별로 담당한다.
- `service/`: UI를 모르는 비즈니스 기능을 정의한다.
- `tools/`: 선택, paint stroke, patch transform 등 개별 도구의 상태와 계산만 담당한다.
- `core/`: 이미지 IO, 공통 geometry, MapSet, project, logging 등 기반 기능을 담당한다.

## 가벼운 기능

짧게 끝나는 기능은 MainWindow가 서비스를 직접 호출하고 결과를 UI에 반영한다.

```text
button/menu/canvas
  -> MainWindow
       -> service
            -> core
       -> UI/canvas update
```

예:

- 단일 이미지 전처리 미리보기
- label txt 로드와 현재 라벨 상태 갱신
- 작은 ROI 계산
- label catalog 편집

## 무거운 기능

UI가 `operation + payload` 신호를 보내면 app이 해당 기능 worker를 생성한다.
worker는 직접 서비스를 호출하고 progress/result/error signal을 app과 UI에 전달한다.

```text
MainWindow._request_worker(operation, payload)
  -> task_requested signal
     -> DatasetEditorApp._start_worker
        -> feature QThread
           -> service/core
        -> progress/succeeded/failed/cancelled
           -> MainWindow UI update
```

worker 구분:

- `ProjectWorker`: dataset scan, MapSet 저장, defect pool 입출력
- `EditingWorker`: MapSet healing, manual Poisson 합성
- `AugmentationWorker`: preview, AutoAugment, orientation augmentation
- `ExportWorker`: YOLO dataset export와 검증
- `BaseWorker`: 공통 취소 플래그, 진행률 정규화, 예외 signal 변환

별도 범용 작업 관리자 계층은 두지 않는다. app이 concrete worker 인스턴스를 직접 소유한다.

## 도구 흐름

`ui/tool_controller.py`가 Qt mouse event와 UI 갱신을 담당한다.
`tools/*.py`는 canvas나 MainWindow를 참조하지 않고 도구 상태와 계산 결과만 반환한다.

```text
ImageCanvas mouse event
  -> ui.ToolController
     -> active tools/*.py
     -> MainWindow/canvas update
```

`ToolController`는 UI 계층이므로 canvas와 MainWindow를 직접 사용할 수 있다.
도구 이벤트 조정을 `service/`에 두지 않는다.

## 의존 방향

```text
main -> app
app -> ui / worker / service
ui -> service / core / tools / config
worker -> service / core / config
service -> core / config
tools -> core
core -> config
```

금지 방향:

```text
ui -> worker
service -> ui / worker / tools
tools -> ui / worker / service
worker -> ui / tools
core -> ui / worker / service / tools
```

이 규칙은 `tests/test_architecture_boundaries.py`가 AST import 검사로 고정한다.

## 현재 폴더 구조

```text
Dataset-Editor/
├─ main.py
├─ app.py
├─ config/
├─ core/
├─ service/
│  ├─ augmentation_service.py
│  ├─ editing_service.py
│  ├─ history_service.py
│  ├─ labeling_service.py
│  ├─ preprocessing_service.py
│  ├─ project_service.py
│  ├─ roi_service.py
│  └─ yolo_export_service.py
├─ worker/
│  ├─ base_worker.py
│  ├─ project_worker.py
│  ├─ editing_worker.py
│  ├─ augmentation_worker.py
│  └─ export_worker.py
├─ tools/
│  ├─ label_tools.py
│  ├─ paint_tools.py
│  ├─ patch_tools.py
│  └─ selection_tools.py
└─ ui/
   ├─ imagecanvas.py
   ├─ mainwindow.py
   ├─ tool_controller.py
   ├─ uisetup.py
   └─ dialogs/pages/widgets
```

## 리팩터링 기준

1. UI 업데이트는 MainWindow 또는 UI controller에 둔다.
2. 무거운 서비스 호출은 해당 기능 worker에 둔다.
3. worker 종류를 범용 관리자 하나로 합치지 않는다.
4. 한 줄 전달만 하는 compatibility wrapper는 호출 지점으로 접는다.
5. 같은 파싱·변환 로직은 한 구현만 유지한다.
6. 새 계층 위반은 아키텍처 테스트로 차단한다.
