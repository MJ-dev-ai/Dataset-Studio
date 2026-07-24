# 변경 이력

이 문서는 DatasetStudio의 주요 구현 및 변경 사항을 버전별로 기록합니다.

현재 폴더에는 이전 릴리스 이력이 없으므로, README에 기록되어 있던 구현 상태를
`v0.1.0` 기준선으로 정리했습니다. 이후 작업은 먼저 `Unreleased`에 추가하고,
릴리스할 때 새 버전 항목으로 이동합니다.

## Unreleased

아래 항목은 아직 릴리스되지 않은 개선 계획입니다.

상태 표기:

* **미구현**: 사용자 기능 또는 UI가 아직 없음
* **부분 구현**: 기본 동작은 있으나 적용 범위나 사용성이 제한됨
* **개선**: 기존 기능의 품질 또는 안정성을 높이는 작업

### 이미지 편집 및 합성 품질

* **개선** Poisson 합성 경계 품질 개선
  * 회전·확대된 마스크의 보간 테두리 제거
  * 마스크 침식, feathering 및 임계값 옵션 추가
  * `NORMAL_CLONE`과 `MIXED_CLONE` 결과 비교 및 자동 선택
  * 강한 모서리나 구조선을 가로지르는 배치 감지
* **개선** 합성 결과 품질 검사 및 실패 원인 기록 강화
  * Poisson 실패 시 hard paste fallback 발생 여부 표시
  * 경계 불연속, 과도한 명암 차이, 빈 마스크 자동 검사
  * 미리보기에서 원본·마스크·합성 결과 비교
* **부분 구현** Fill 기능 개선
  * 현재 선택 영역 또는 전체 이미지를 단색으로 채우는 수준
  * 색상 허용 오차를 사용하는 flood fill과 연결 영역 채우기 추가
* **미구현** 실제 Blur / Smooth 브러시 구현
* **미구현** Threshold 도구의 캔버스 직접 적용 및 실시간 미리보기
* **개선** Patch 회전·크기 조정 시 이미지와 마스크의 정렬 정확도 향상

### 선택, 마스크 및 클립보드

* **개선** Rectangle / Polygon / Lasso 선택 편의성 개선
  * 선택 영역 이동·확대·축소 및 꼭짓점 편집
  * 선택 더하기, 빼기, 교집합 모드
  * Polygon 작성 중 마지막 점 취소 및 키보드로 완료
  * 선택 영역 반전, feather, grow/shrink
* **미구현** Brush Mask 및 Eraser Mask 도구
* **미구현** Selection to Mask / Mask to Selection 변환
* **미구현** Mask 기반 Bounding Box 자동 생성
* **부분 구현** 내부 patch clipboard 메타데이터 및 상호 운용성 확장
  * clipboard 항목에 명시적인 class ID와 사용자 태그 보존
  * 운영체제 클립보드와 이미지 복사·붙여넣기 연동

### Undo / Redo 및 편집 이력

* **부분 구현** Undo / Redo 적용 범위 확대
  * 현재는 주로 캔버스 픽셀 변경을 이미지 스냅샷으로 저장
  * 라벨 생성·삭제·이동, 선택 변경, patch 배치, 전처리에도 적용
  * 작업 이름이 표시되는 History 패널 추가
  * 대형 이미지에서 메모리를 줄이기 위한 delta 기반 이력 검토
* **개선** 저장되지 않은 변경 사항 표시와 종료 전 저장 확인
* **개선** 이미지·라벨·프로젝트의 dirty 상태를 각각 추적

### 프로젝트 저장, 복구 및 경로 관리

* **부분 구현** Project 저장 및 로드 범위 확대
  * 현재 root folder, 현재 MapSet·이미지, MapSet 목록과 ROI contour 저장
  * 선택 영역, zoom/pan, 활성 도구, 열려 있는 탭과 UI 배치 저장
  * 전처리·증강·내보내기 옵션과 label catalog 상태 저장
  * 이동되거나 누락된 파일 경로의 재연결 기능
* **미구현** 최근 프로젝트 목록과 시작 화면
* **미구현** 이전에 선택한 입력·출력 경로 저장 및 자동 복원
* **미구현** 자동 저장, 비정상 종료 복구 및 백업 파일 관리
* **개선** 프로젝트 파일 버전과 마이그레이션 규칙 추가

### 작업 진행 상태 및 백그라운드 실행

* **부분 구현** 장시간 작업 Progress UI 확대
  * AutoAugment 외 전처리·내보내기·저장 작업에도 일관된 progress panel 적용
  * 처리량과 예상 잔여 시간 표시
  * 여러 작업의 대기·실행·완료·실패 상태를 보여주는 작업 목록
* **개선** 모든 장시간 작업에 일관된 Cancel / Retry 동작 제공
* **개선** 작업 완료 후 결과 폴더 열기와 실패 항목 재실행
* **개선** 대량 작업 전 예상 생성 파일 수와 디스크 사용량 안내

### GUI 및 사용성

* **개선** 버튼과 QAction의 Enable / Disable 상태 분기 통합
  * 프로젝트, 이미지, 선택, patch, 실행 중 작업 상태에 따라 일관되게 갱신
  * 실행할 수 없는 이유를 tooltip 또는 상태 메시지로 안내
* **개선** Main UI 및 Dialog 외형과 크기 조절 동작 개선
* **미구현** Shortcut 편집 창
  * 중복 단축키 검사, 기본값 복원, 사용자 설정 저장
* **미구현** About 페이지
  * 현재 About 액션은 상태바에 애플리케이션 이름만 표시함
  * 버전, 라이선스, 사용 라이브러리 및 로그 폴더 링크 제공
* **개선** 빈 화면과 오류 화면에 다음 행동을 안내하는 메시지 추가
* **개선** 파괴적 작업과 덮어쓰기의 확인 및 결과 요약 일관화

### 환경 설정 및 국제화

* **미구현** 한국어 / 영어 언어 선택과 런타임 전환
* **미구현** 사용자 설정 저장
  * 테마, 언어, 최근 경로, 창 크기·위치, dock 배치, 단축키
* **개선** 이미지 편집·Poisson·전처리 기본값을 preset으로 저장 및 불러오기
* **개선** 설정 초기화와 설정 내보내기·가져오기

### 로그, 오류 처리 및 진단

* **부분 구현** 크래시 및 작업 로그 확장
  * 회전 로그, pending crash 기록, Jobs 로그 패널은 구현됨
  * 작업 ID, 입력, 옵션, 처리 시간, 성공·실패 개수 기록 추가
* **개선** 사용자 메시지와 상세 개발자 오류를 분리
* **개선** 로그 복사, 로그 폴더 열기 및 진단 보고서 생성
* **개선** 실패한 파일만 CSV 또는 JSON으로 내보내기

### 라벨링 및 데이터 검증

* **미구현** Bounding Box 이동 및 크기 조정 핸들
* **개선** 라벨 저장 전 범위 초과, 0 크기, 잘못된 class ID 검사
* **개선** 이미지와 라벨 누락, 중복 이미지, 빈 라벨을 보여주는 Dataset Health Check
* **개선** 클래스별 개수와 train / val / test 분포 시각화
* **개선** Poisson 합성 label과 실제 mask/bounding box의 일치 여부 검사

### 테스트, 배포 및 문서

* **개선** Project 저장·복구, Undo / Redo, 사용자 설정의 통합 테스트 추가
* **미구현** Windows 실행 파일 패키징과 버전 정보 자동 반영
* **개선** 사용자 작업 흐름별 도움말과 단축키 안내 문서 추가

## v0.3.0 - 2026-07-02

### AutoAugment 합성 및 배치 안정성

* Poisson 기반 자동 합성에 `Boundary Mixed` 모드 추가
  * 결함 패치를 마스크로 직접 붙여 넣은 뒤 마스크 내부 경계에만 `MIXED_CLONE` 적용
  * 마스크 바깥 원본 픽셀은 OpenCV 결과와 무관하게 항상 원본 값으로 유지
  * 마스크 중심부는 보정된 패치를 직접 복원하여 얇은 균열과 작은 결함의 소실 방지
* Boundary 폭을 고정 픽셀값 대신 패치 짧은 변의 5%로 계산하도록 변경
  * 최소 2px, 최대 255px 범위 적용
  * 얇은 결함에서는 실제 결함 두께의 25%를 넘지 않도록 내부 경계 폭 제한
* 합성 패치의 색감 정합 추가
  * 흑백 이미지는 밝기 중앙값을 대상 위치에 60% 정합
  * 컬러 이미지는 채널별 중앙값을 대상 위치에 60% 정합
  * alpha blending 없이 보정된 패치를 직접 Paste하는 구조 유지
* 기존 `Normal`, `Mixed`, `Detail Preserve` 모드를 계속 선택할 수 있도록 호환성 유지
* 실험적으로 추가했던 Diffusion Inpaint 코드, 의존성 및 모델 캐시 제거

### ROI 및 다중 결함 배치

* 패치의 활성 영역이 ROI contour 안에 완전히 포함되는 위치만 선택하도록 배치 검사 강화
* 기존 라벨과 같은 이미지에 먼저 합성된 결함을 점유 영역으로 취급하도록 변경
* 패치 크기에 비례한 최소 간격과 다중 위치 재탐색을 적용하여 결함 중첩 및 군집 배치 방지
* 충돌 없이 배치할 공간이 없으면 억지로 겹쳐 붙이지 않고 해당 결함 생성을 건너뛰도록 처리
* ROI 포함 및 충돌 검사 시 전체 마스크 연산 비용을 줄이기 위해 활성 bounding rectangle 기반 후보 계산 적용

### 수동 Patch Clipboard 및 MapSet 편집

* 여러 패치를 동시에 보관할 수 있는 내부 Patch Clipboard 구현
* patch image, mask, source path와 MapSet별 정렬된 map image를 하나의 clipboard 항목으로 보존
* clipboard thumbnail을 캔버스로 드래그하여 원하는 위치에 패치를 배치하도록 지원
* 마우스 우클릭 드래그를 통한 패치 회전과 기존 이동·크기 조정 동작 통합
* Poisson 적용 후 다음 클릭에서 새 패치가 생성되거나 도구가 비정상 종료되는 문제 수정
* Defect Pool의 `class/id_map.png` 구조를 분석하여 추출된 결함을 Patch Clipboard로 일괄 가져오는 기능 추가
* Defect Pool 읽기를 background task로 실행하여 대량 패치 로딩 중 UI 응답성 유지
* 수동 `Boundary Mixed` 합성을 MapSet의 모든 정렬된 map에 적용하고 새 MapSet으로 저장하도록 연결

### MapSet 저장 및 데이터 내보내기

* 편집 결과 저장 단위를 단일 이미지가 아닌 MapSet 전체로 통일
* 원본 MapSet을 변경하지 않고 새 MapSet으로 저장하는 transactional export 경로 추가
* 현재 MapSet 전체 맵의 편집 상태를 함께 저장하고 프로젝트 트리와 속성 패널을 갱신하도록 개선
* YOLO TXT 내보내기 시 라벨이 없는 이미지에도 대응하는 빈 `.txt` 파일 생성

### YOLO 학습 파이프라인

* 학습 데이터 경로가 Ultralytics 기본 `coco8.yaml`로 조용히 대체되지 않도록 custom `data.yaml` 경로 고정
* `utils/yolo_dataset_tools.py`와 `config/yolo_train_config.py`의 dataset resolution 및 train argument 구성 정리
* 기존 train / val / test split을 유지하면서 증강된 데이터셋을 학습 파이프라인에서 직접 사용하도록 개선
* 원본 데이터가 적은 환경에서도 test split에는 학습 증강을 혼입하지 않는 데이터 누수 방지 원칙 유지

### 테스트 및 오류 처리

* Boundary Mixed의 중심 보존, 얇은 균열 유지, 마스크 외부 원본 불변성 테스트 추가
* 컬러·흑백 패치 보정, ROI 완전 포함, 기존 라벨 충돌 회피 테스트 추가
* Defect Pool MapSet grouping과 다중 Patch Clipboard 소유권 테스트 추가
* 수동 MapSet Poisson 입력, MapSet 저장 및 빈 YOLO label export 테스트 보강
* 장시간 수동 합성·Defect Pool import를 TaskManager background worker로 실행
* 작업 실패를 UI status와 crash log에 전달하고 작업 완료 시 control state를 복구하도록 개선

## v0.2.0 - 2026-06-26

### AutoAugment Dialog UI 개편

* AutoAugment 화면을 메인 workspace page가 아니라 modeless popup dialog로 변경
* `ui/autoaugment.ui`를 Designer 기반 단일 UI 소스로 사용하도록 연결
* 프로젝트 공통 테마와 동일한 스타일을 사용하도록 QFrame / QGroupBox 카드 배경, border, radius 적용
* Light / Dark theme 전환 시 카드 배경과 텍스트 색상이 자동 반영되도록 개선
* dialog 기본 크기와 최소 크기를 축소하여 화면 점유율 완화
* Target Map 선택 콤보박스는 항상 유지하고, Dataset / ROI 요약 정보는 `Details` 팝업으로 이동

### AutoAugment 설정 및 미리보기 개선

* Poisson Balance의 `Same-class Max`를 ComboBox에서 SpinBox로 변경
* Poisson mode 선택값인 `Mixed` / `Normal`이 AutoAugment 생성 파이프라인에 실제 반영되도록 연결
* Random / Flip / Rotation / Split / Poisson sample 값 변경 시 preview summary가 즉시 갱신되도록 정리
* Planned Output이 augmentation factor를 반영하도록 수정
  * Train: `base train × flip × rotation × random`
  * Val: `base val × flip × rotation`
  * Test: base test count 유지
* Preview 영역과 Results 영역의 비율을 재조정하고, 결과 영역이 항상 보이도록 변경

### AutoAugment 진행률 및 결과 표시

* AutoAugment 진행 상태를 로그창 중심이 아니라 dialog 하단 progress panel에 표시
* progress panel을 항상 표시하고, 실행 전 기본 상태를 `Ready`와 `0%`로 초기화
* Generate 시작 시 Results 값을 초기화하지 않도록 변경
* 작업 단계별 진행 문구를 한 줄 상태 메시지로 정리
  * 입력 준비
  * Poisson sample 생성
  * train / val / test split
  * train / val / test output writing
  * finalizing
* Generate 완료 후 Results 패널에 생성 결과 요약 표시
  * total images
  * total labels / annotations
  * poisson samples
  * train / val / test output count
  * failed / skipped count
* Results 상단 4개 preview slot 개선
  * 앞 3개 slot에는 실제 생성된 output image thumbnail 표시
  * 마지막 slot에는 `+9,999` 형식으로 나머지 이미지 수 표시
* Final Class Distribution은 최종 결과이므로 `현재 → 목표` 형식 대신 최종 숫자만 표시
* 현재 dataset class 구조에 따라 result distribution progressbar maximum과 row label을 갱신하도록 개선

### Poisson Editing 및 Patch 합성

* 수동 Poisson editing에서도 toolbar 선택값을 읽어 `Normal` / `Mixed` clone mode를 적용하도록 변경
* Poisson clone mode 문자열을 OpenCV clone flag로 변환하는 공통 helper 추가
* AutoAugment와 수동 Poisson editing이 동일한 clone mode 해석 로직을 사용하도록 정리

### AutoAugment 생성 결과 데이터

* AutoAugment 결과 dict에 실제 저장된 sample image path 목록(`sample_images`) 추가
* 기존 대표 이미지(`preview_image`) 반환은 유지하여 기존 호출부와 호환성 보존
* 저장 성공한 output image만 Results preview sample로 사용하도록 처리
* output write 실패 시 예외를 명시적으로 발생시켜 실패 집계와 결과 표시의 신뢰성 개선

### 문서 및 변경 이력

* README에 있던 개발 상태 / 수정 사항 내용을 CHANGELOG 기준으로 분리
* 개선 사항을 기능 범주별로 재정리
* AutoAugment, Poisson Editing, UI 진행률, 미구현 / 개선 예정 항목을 버전 기록에 반영

## v0.1.0 - 2026-06-25

### 애플리케이션 기반

* 기본 PyQt6 GUI 구조
* `mainwindow.ui` 기반 UI 로딩
* 메뉴, 툴바, 패널 연결 및 아이콘 적용 구조
* 고대비 Dark / Light 테마 전환
* 미처리 예외 회전 로그 및 `logs/pending_crash.log` durable flush
* Autoaugmentation Dialog 새로 디자인

### 프로젝트 탐색 및 이미지 표시

* 폴더, MapSet, 맵 파일을 표시하는 계층형 Project Explorer
* Albedo, Normal, Curvature 맵 전환 탭
* 맵 간 zoom, pan, selection, label overlay 및 normalized viewport 동기화
* 커서 기준 wheel zoom과 Move tool/가운데 버튼 pan
* 메모리 상한 LRU `PixmapCache` 및 OpenCV 이미지 캐시

### 선택 및 이미지 편집

* Rectangle, Polygon, Lasso 선택과 선택 overlay
* Brush, Eraser, Fill 픽셀 편집
* 메모리 예산형 Undo / Redo 이력
* Patch 이동, 회전, 배율 변경
* Hard paste 및 Poisson blend

### 라벨링 및 결함 내보내기

* Select 툴바의 Add Label, Save YOLO, Export Defect, Copy Patch
* 클래스 ID와 이름을 관리하는 Label Class Manager
* 기존 클래스 콤보를 사용하는 Add Label 팝업
* Canvas annotation 선택 및 Remove Label/Delete 삭제
* YOLO label 로드, 생성, 저장, overlay
* 동일한 선택 좌표를 사용하는 다중 map defect export

### 전처리 및 증강

* CLAHE, Sharpen, Threshold 일괄 전처리
* Auto ROI contour 기반 Poisson 자동 증강
* Class imbalance 보정
* Albumentations 기반 map/label 동기 orientation augmentation
* Normal / Mixed Paste 기능 구현

### 데이터셋 내보내기

* Train / Val / Test 분할
* Map별 YOLOv8 데이터셋 내보내기

### 백그라운드 작업 안정성

* Dataset scan, preprocessing, augmentation, export의 백그라운드 실행
* `core/taskmanager.py` 중심의 장시간 작업 관리
* `TaskContext`를 통한 취소 상태 및 진행률 전달
* 종료 시 cooperative cancellation 및 모든 QThread 회수
* 실행 중인 thread가 정리되기 전 창 종료 방지
