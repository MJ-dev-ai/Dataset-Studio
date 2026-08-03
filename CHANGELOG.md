# 변경 이력

**Dataset Editor**의 핵심 변경 사항만 버전별로 기록합니다.

`v0.1.0`부터 `v0.3.0`까지는 2026년 7월 24일 Git 저장소 이관 시 README와
기존 개발 기록을 기준으로 복원한 이력입니다. 이후 변경 사항은 먼저
`Unreleased`에 기록하고, 릴리스 시점에 버전 항목으로 이동합니다.

## Unreleased

* Poisson / Boundary Mixed 합성 품질, 실패 원인 기록, 마스크·선택 편집 개선
* 프로젝트 저장·복구, Undo / Redo 범위, dirty 상태 추적 강화
* 장시간 작업의 진행률, 취소·재시도, 결과 요약 UI 개선
* 라벨 검증, Dataset Health Check, 클래스 분포 시각화 보강
* 사용자 설정, 다국어, 도움말, Windows 패키징 정리

## 저장소 이관 - 2026-07-24

* 기존 소스, UI 리소스, 설정, 문서 및 테스트를 Git 초기 커밋으로 등록
* README에 흩어져 있던 구현 이력을 `CHANGELOG.md` 기준으로 정리
* Python 가상환경, 캐시, 분석 산출물, 학습 출력물이 Git 변경 목록에 섞이지 않도록 `.gitignore` 정리

## v0.3.0 - 2026-07-02

* Poisson 자동 합성에 `Boundary Mixed` 모드 추가
* ROI 내부 배치, 기존 라벨 충돌 회피, 다중 결함 간격 검사를 강화
* 다중 Patch Clipboard, Defect Pool 일괄 가져오기, 수동 MapSet 합성 추가
* MapSet 단위 저장과 빈 YOLO label export 지원
* YOLO 학습 파이프라인의 `data.yaml` 고정, split 유지, test leakage 방지
* Boundary Mixed, ROI / 충돌 검사, Patch Clipboard, MapSet 저장·내보내기 테스트 보강

## v0.2.0 - 2026-06-26

* AutoAugment를 modeless dialog로 분리하고 UI, 테마, 레이아웃 정리
* Poisson mode, Same-class Max, planned output, preview summary 반영 개선
* Progress / Results panel을 추가해 단계별 진행률과 생성 결과 표시
* 수동 Poisson editing과 AutoAugment의 clone mode 해석 로직 통합
* 생성 결과 sample image 목록과 실패 집계를 명확히 반환

## v0.1.0 - 2026-06-25

* PyQt6 기반 Dataset Editor GUI, Project Explorer, map tabs, dark / light theme 구축
* Map 간 viewport 동기화, zoom / pan, selection, label overlay, image cache 구현
* Rectangle / Polygon / Lasso 선택, Brush / Eraser / Fill, Undo / Redo, Patch / Poisson editing 구현
* Label Class Manager, YOLO label load / save / export, defect export 추가
* CLAHE / Sharpen / Threshold 전처리, ROI 기반 자동 증강, class imbalance 보정 구현
* Train / Val / Test split, YOLOv8 dataset export, background task manager 및 취소 처리 구축
