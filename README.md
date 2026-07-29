# 소량 화물 운송수단 비교 플랫폼 (프로토타입)

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

## 파일 구조

- `app.py` — Streamlit UI, 전체 흐름 담당
- `geocode.py` — Google Geocoding API (주소 → 좌표)
- `road_cost.py` — 카카오맵 API 기반 트럭 소요시간(실시간) + 트럭/퀵 요금 근사
- `rail_freight_nodes.py` — 화물역 좌표, 철도 근사 상수
- `rail_cost.py` — 화물역 간 근사 소요시간/운임 계산
- `ktx_tucking.py` — KTX특송 규격/노선/취급역 판정
- `consolidation.py` — 소량 화물 통합(규칙 기반 그룹핑) 핵심 로직
- `gemini_assist.py` — 자연어 입력 파싱 + 결과 설명 생성 (역할 제한적으로 사용)

## 제출 전 반드시 확인/보정할 것 (코드 내 TODO 표시됨)

1. `rail_freight_nodes.py`의 `RAIL_TON_KM_RATE_WON`, `AVG_FREIGHT_SPEED_KMH`
   — 근거 자료로 보정
2. `road_cost.py`의 트럭/퀵 요금 계수
   — 국토부 화물 표준운임 가이드라인 참고해 보정
3. `ktx_tucking.py`의 `base_fare_won`, `KTX_TUCKING_STATIONS`
   — https://zimcarry.net 최신 공시 요금표/취급역 목록으로 교체
4. `app.py`의 KTX특송 역 매핑 로직
   — 현재는 데모용으로 단순화되어 있음 (실제 주소 → 취급역 매핑 필요)
5. TAGO API는 아직 연동 안 됨 — 여객열차 시각표 참고용으로 추가하려면
   기존 여객 프로젝트의 `train_api.py`를 참고해 통합 가능

## 알려진 한계

- 화물열차 실제 시각표/운임은 비공개(LOGIS 내부 시스템)라 전부 근사치
- 데모용 가상 화주 풀(`get_mock_pool`)은 실제 누적 주문이 아닌 하드코딩 예시
- KTX특송 취급역·요금은 시기별 변동이 있어 최신 확인 필수
