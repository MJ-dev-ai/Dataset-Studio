# Dataset Studio / CVAT 라벨링·UI 비교와 적용

작성일: 2026-10-23. 문서·소스·한글 클래스 저장은 UTF-8로 확인했다.

## 분석 기준

- CVAT 별도 클론: `C:/Users/tnsmi/Downloads/cvat-analysis`
- 분석 커밋: `641073751e9a25790e2a26e18f8068d8f74f1be8` (develop, shallow clone)
- 비교 대상: Dataset Studio의 Python/PySide6 캔버스, YOLO 바운딩 박스, 도구 선택, 우측 속성 패널과 이력 처리.
- 비교 기준: 작업 반복성, 선택 상태의 명확성, 취소·복원 정확도, 저장 결과의 일관성. 언어 간 밀리초 비교는 하지 않았다. CVAT 서버를 띄우거나 설치본을 실측한 결과가 아니라 저장소 소스 분석이다.
- CVAT 코드를 직접 이식하지 않고 기존 Qt 구조에 맞게 동작을 구현했다. CVAT의 모든 기능을 도입한 것은 아니다.

## 소스 근거와 적용 판단

| CVAT 소스 | 확인한 동작 | Dataset Studio의 문제와 개선 |
|---|---|---|
| [controls-side-bar.tsx](https://github.com/cvat-ai/cvat/blob/641073751e9a25790e2a26e18f8068d8f74f1be8/cvat-ui/src/components/annotation-page/standard-workspace/controls-side-bar/controls-side-bar.tsx#L93) | N으로 직전 그리기 설정을 재사용 | 기존 W는 드래그 후 클래스 관리 대화상자를 열었다. 이제 상단에서 클래스를 고르고 연속으로 박스를 그린다. W 유지, N 추가 |
| [canvas-wrapper.tsx](https://github.com/cvat-ai/cvat/blob/641073751e9a25790e2a26e18f8068d8f74f1be8/cvat-ui/src/components/annotation-page/canvas/views/canvas2d/canvas-wrapper.tsx#L312) | Tab/Shift+Tab 객체 탐색과 단축키 범위 지정 | 캔버스의 M/W 모드에서 객체를 순환한다. 입력창의 Tab·문자 입력은 유지 |
| [objects-list.tsx](https://github.com/cvat-ai/cvat/blob/641073751e9a25790e2a26e18f8068d8f74f1be8/cvat-ui/src/containers/annotation-page/standard-workspace/objects-side-bar/objects-list.tsx#L105) | 선택 객체와 삭제·표시·잠금 명령 연결 | 우측 객체 목록, 선택 객체 클래스/좌표, 표시 체크박스, 명시적 삭제 버튼 추가. H/L은 기존 이동/올가미와 충돌하므로 가져오지 않음. 객체별 잠금은 이번 범위에서 제외 |
| [objectSelector.ts](https://github.com/cvat-ai/cvat/blob/641073751e9a25790e2a26e18f8068d8f74f1be8/cvat-canvas/src/typescript/objectSelector.ts) | 숨긴 객체를 선택 후보에서 제외하고 선택 조건을 명시 | 숨긴 라벨의 클릭 선택 방지. 겹친 박스는 Ctrl+클릭으로 순환하도록 Dataset Studio에 맞게 설계 |
| [annotations-history.ts](https://github.com/cvat-ai/cvat/blob/641073751e9a25790e2a26e18f8068d8f74f1be8/cvat-core/src/annotations-history.ts#L154) | 여러 변경을 하나의 트랜잭션으로 묶고 취소 시 되돌림 | 박스 이동/크기 조절을 한 번의 Undo로 기록. Esc·포커스 이탈·도구 전환 시 진행 중 좌표 복원. 픽셀 이력과 라벨 이력 분리 |

## 실제 변경

### 라벨링 흐름

1. 상단 **새 라벨**에서 클래스를 선택한다. 클래스가 없다면 우측 **클래스 관리**에서 등록한다.
2. W 또는 N으로 박스를 그린다. 드래그를 끝내면 즉시 라벨이 생성되고 같은 클래스로 계속 그릴 수 있다. 이미지 밖 시작·면적 없는 클릭은 라벨을 만들지 않는다.
3. M 또는 우측 목록으로 객체를 선택한다. 박스 안을 드래그하면 이동하고 핸들을 드래그하면 크기가 바뀐다. Ctrl+클릭으로 겹친 객체를 순환한다.
4. 우측 클래스와 X/Y/너비/높이를 편집하고 **선택 객체에 적용**을 누르면 하나의 변경으로 기록한다. 선택 객체의 클래스 변경은 다음 박스의 클래스 선택을 바꾸지 않는다.
5. **라벨 저장**은 기존 MapSet의 YOLO 파일로 저장한다. 독립 이미지에서도 라벨을 편집할 수 있지만 저장에는 기존 MapSet 흐름이 필요하다.

기존 사각형·다각형·올가미 선택에서 **선택 → 라벨**도 사용할 수 있다. 현재 저장 형식은 바운딩 박스이므로 비사각형 선택은 외접 사각형으로 저장된다.

### UI 연결

- 상단은 새 라벨의 클래스, 우측은 현재 선택한 객체의 속성을 담당한다. 캔버스·목록·속성이 같은 객체를 가리킨다.
- 목록에 번호·클래스·크기, 상단에 객체 수·미저장 상태를 표시한다.
- 캔버스에서 클래스별 색, 선택 객체 강조색, 어두운 배경의 한글 이름으로 구분한다. 박스 그리기에는 십자 안내선을 표시한다.
- 우측 패널의 숫자 입력·버튼 폭을 조정해 1440×900 화면의 기본 도크 폭에서 잘리지 않도록 확인했다. 긴 패널은 기존 세로 스크롤을 사용한다.
- 중복된 삭제 버튼은 숨기고 데이터셋 작업을 객체 속성과 구분했다.

### 단축키

| 키 | 동작과 범위 |
|---|---|
| W / N | 새 바운딩 박스 도구, 현재 클래스 재사용 |
| M | 사각형 선택 및 기존 박스 이동·크기 조절 |
| Ctrl+클릭 | M에서 포인터 아래 겹친 객체 순환 |
| Tab / Shift+Tab | M/W에서 다음 / 이전 객체 |
| 방향키 / Shift+방향키 | M/W에서 선택 객체 1px / 10px 이동, 이미지 경계에서 크기 유지 |
| Delete | M/W 캔버스 또는 객체 목록에서 선택 객체 삭제. 미선택 상태에서 임의 박스를 지우지 않음 |
| Esc | 진행 중 박스 작업 취소 또는 객체 선택 해제 |
| Ctrl+Z / Ctrl+Shift+Z | 라벨 편집 문맥에서 라벨 Undo/Redo. 드래그 중 Undo는 현재 드래그만 취소 |

입력창에서는 문자 입력·기본 편집 키를 유지한다. 기존 H 이동, L 올가미, Space 임시 이동 등과 충돌하지 않게 구성했다. 라벨 편집 문맥은 W 모드, 또는 선택 도구에서 선택 객체/라벨 이력이 있는 상태다. 그 밖의 이미지 편집 문맥에서는 기존 픽셀 Undo를 사용한다.

### 상태와 저장 정확도

- `ui/imagecanvas.py`: 라벨 데이터·선택·최대 32개 라벨 이력의 소유자. 드래그 중에는 시작 스냅샷 하나를 유지하고 확정 때만 변경 신호를 보낸다.
- `tools/toolmanager.py`: 입력 문맥·드래그·취소를 담당한다.
- `ui/annotation_panel.py`: 목록과 입력 표시를 담당하며 별도 라벨 복사본을 소유하지 않는다.
- `ui/mainwindow.py`: 카탈로그·MapSet·YOLO 저장을 담당한다. 문서 재로딩과 좌표계를 바꾸는 변환에서는 과거 라벨 이력을 초기화한다.
- 같은 박스를 다시 선택하거나 변경 없는 속성을 적용해도 편집 이력이 늘지 않는다. 이동 중 매번 픽셀 이미지를 복사하지 않는다.
- 미저장 표시는 보수적인 편집 플래그다. Undo로 저장 당시 값에 돌아왔는지를 비교하는 저장 지점 추적 기능은 이번에 추가하지 않았다.

## 검증

- `tests/test_cvat_labeling.py`: Qt 이벤트로 연속 생성, 빈 클릭, 경계, 겹침, 목록 동기화, 속성·클래스 변경, 이동·리사이즈, 취소, 라벨 Undo/Redo, 숨김, 입력창 키 보호, 빈 파일 재로딩, UTF-8 클래스와 YOLO 저장/재로딩을 검사했다.
- 관련 회귀 검사: **98 passed, 1 deselected**. 새 라벨링 17개와 기존 도구·패치·healing·합성 관련 검사를 포함한다. 다른 문서에서 돌아왔을 때 캐시된 미저장 라벨과 패널 상태가 함께 복원되는지도 검사했다.
- 제외한 기존 검사: `test_fast_healing_preview_uses_lightweight_composite`. 기존 테스트가 현재 지원하지 않는 `fast_preview=True` 인자를 요구한다. 이 검사는 통과한 것으로 계산하지 않았다.
- 전체 저장소 테스트 통과를 주장하지 않는다. 구형 PyQt6/모듈·학습 의존성으로 인한 기존 수집 오류가 있는 전체 테스트 대신 변경에 직접 관련된 검사를 실행했다.
- `perf/capture_cvat_labels.py`로 합성 이미지와 한글 클래스(표면 균열·찍힘·이물질)를 사용해 offscreen Qt 렌더링을 확인했다. 사용자 데이터는 사용하지 않았다. 실제 모니터의 DPI·운영체제 입력기까지 검증한 것은 아니다.
- 화면: `perf/cvat-label-draw.png`, `perf/cvat-label-edit.png`.

CVAT의 서버·팀 검수·동영상 추적·자동 라벨링·객체별 잠금·다중 객체 편집·폴리곤/마스크 저장은 추가하지 않았다. 특히 현재 YOLO 박스 데이터 모델을 유지하므로 비사각형 라벨 편집은 별도의 저장 형식과 이력 설계가 필요하다.

후속 정리 요청에 따라 이전 `photocraft-analysis` 클론 폴더는 삭제했다. 기존 PhotoCraft 비교 보고서와 Dataset Studio의 합성·healing 개선은 보존했다.
