# 소량 화물 운송수단 비교 & Door-to-Door 조율 플랫폼 (프로토타입)

화주의 견적 비교(트럭/퀵/KTX특송/철도 통합운송)부터, 철도 통합운송 예약 확정 이후의
실시간 추적·트럭기사 배차·관제센터 KPI까지 이어지는 통합 프로토타입입니다.

원래 두 개의 별도 프로젝트였습니다.
- **Freight** (본 리포의 메인 구조/로직) — 소량화물 통합 견적 비교 엔진
- **Korail Relai** (팀원 아이디어, 화면 구성 논리 활용) — 예약 후 실시간 추적/트럭기사/관제센터 화면

병합하면서 Relai 쪽의 mock(random) 데이터는 전부 제거하고, Freight 엔진이 산출하는
실제 데이터를 공유 저장소(`shared_store.py`)로 넘겨 후단 화면이 그 데이터를 그대로
쓰도록 연결했습니다.

## 실행 방법

```bash
pip install -r requirements.txt
streamlit run app.py
```

API 키는 코드에 직접 넣지 말고 `.streamlit/secrets.toml`에 넣으세요:

```toml
GOOGLE_MAPS_API_KEY = "..."
KAKAO_REST_API_KEY = "..."
GEMINI_API_KEY = "..."
```

## 화면 구성

- `app.py` — 화주용 견적 비교(트럭/퀵/KTX특송/철도 통합운송) + 철도 통합운송 예약 확정
- `pages/1_화주용_실시간추적.py` — 예약 확정된 화물의 door-to-door 진행 상황 추적
- `pages/2_트럭기사용_앱.py` — 배차 안내 + 복귀 화물(공차 방지) 매칭
- `pages/3_관제센터.py` — 전체 예약 현황, 탄소절감·리드타임 등 실측 KPI
- `pages/4_화차배치추천.py` — 서모게이트 ML 모델(LightGBM) 기반 화물-화차 매칭 추천

## 파일 구조 (엔진, Freight 원본 유지)

- `geocode.py` — Google Geocoding API (주소 → 좌표)
- `road_cost.py` — 카카오맵 API 기반 트럭 소요시간(실시간) + 트럭/퀵/드레이지 요금 근사
- `rail_freight_nodes.py` — 화물역 좌표, 철도 근사 상수 (실제 화물열차 시각표 데이터 기반 선정, 7개 역)
- `rail_schedule.py` — 실제 화물열차 시각표(data.go.kr) 파싱 및 열차 조회
- `rail_cost.py` — 화물역 간 소요시간/운임 계산
- `intermodal.py` — 첫마일(트럭)+철도+막판마일(트럭) door-to-door 계산
- `ktx_tucking.py` — KTX특송 규격/노선/취급역 판정
- `consolidation.py` — 소량 화물 통합(규칙 기반 그룹핑) 핵심 로직
- `cargo.py` — 화물 종류 분류(키워드) 및 요금 할증/수단 제한
- `emission.py` — 배출량(GWP/PM) 및 탄소 마일리지 계산
- `gemini_assist.py` — 자연어 입력 파싱 + 결과 설명 생성 + 화물종류 분류 (역할 제한적으로 사용)
- `freight_train_schedule.csv` — 코레일 실데이터 "2026년도 화물열차 설정 현황"(2026-08-01 기준, 사용자 제공) 가공본. 시발역→종착역 직행 단위 202건

## 파일 구조 (신규 — 병합 시 추가)

- `shared_store.py` — 화주 예약(app.py) → 트럭기사 앱/관제센터가 참조하는 세션 간 공유 저장소.
  `st.cache_resource` 기반 인메모리 저장이라 프로세스 재시작 시 초기화됨 (데모 스코프의 한계, TODO: 영속화)
- `pages/*.py` — Relai의 화면 구성 논리를 가져오되, 데이터는 전부 `shared_store`/Freight 엔진에서 실측으로 가져옴
- `car_assignment.py`, `car_assignment_model.json` — 화차 배치 추천용 서모게이트 LightGBM 모델(사용자가 별도 학습, JS→Python 이식) + mock 화차 편성 생성기
- `utils/data.py` — STATIONS는 `rail_freight_nodes.FREIGHT_NODES`를 그대로 import (중복 정의 방지)

## 알려진 한계 (기존 Freight + 병합 과정에서 추가된 것)

- `freight_train_schedule.csv`는 2026-08-01 기준 스냅샷 — 실시간 시각표 아님, "확정 시각표"로 취급 금지 (그래도 이전 2025-04-14보다 훨씬 최신)
- 데모용 가상 화주 풀(`get_mock_pool`)은 실제 누적 주문이 아닌 하드코딩 예시로 남아 있음 (TODO: 예약 확정 건이 쌓이면 이 풀 자체를 `shared_store`로 대체하는 게 다음 단계)
- 트럭/화차 개별 실시간 GPS는 실제 텔레매틱스 연동 없이는 구현 근거가 없어 관제센터에서 제외 — 대신 화물역별 예약 건수 집계로 대체
- "실시간"은 웹소켓 push가 아니라 각 페이지 새로고침(폴링) 방식. 자동 주기 갱신이 필요하면 `st.fragment(run_every=...)`로 교체 가능 (TODO, 아직 미적용)
- 트럭 단독/퀵서비스/KTX특송 예약 건은 화물역 환적 구간이 없어 실시간 추적·트럭기사 연계 대상에서 제외됨 (철도 통합운송 건만 후단 화면과 연동)
- 화차 배치 추천의 예측 모델 자체는 실제 학습된 것이지만, 학습 라벨(suitability_score)은 코레일 실제 배치 규정이 아닌 자체 정의 합성 데이터. 화차 편성(개별 화차 종류/적재량/위치)도 실제 데이터가 없어 열차번호 기반 결정론적 mock으로 생성 (car_assignment.generate_mock_train_composition)
