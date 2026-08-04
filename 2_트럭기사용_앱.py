# -*- coding: utf-8 -*-
"""트럭기사용 앱 — 배차 안내 + 복귀 화물(공차 방지) 매칭 + 예상 수익.

⚠️ "결합적합도" 점수는 학습된 모델이 아니라 명시적 규칙(가중합) 기반
   점수다. Freight의 consolidation.py가 쓰는 결합 최소기준
   (MIN_CONSOLIDATION_TON)을 그대로 가져와 "이 화물이 결합운송 기준에
   얼마나 가까운가"를 점수화한다.
⚠️ 점수에 대한 "AI 설명"은 Gemini가 생성하지만, 점수 자체를 계산하지는
   않는다 — 숫자는 규칙이 만들고 AI는 그 근거를 문장으로 풀어줄 뿐이다.
   같은 입력이라도 문구는 호출마다 달라질 수 있다(재현성 낮음).
⚠️ 기사 현재 위치는 실제 GPS 연동이 없어 utils/data.py에
   DRIVER_CURRENT_STATION으로 하드코딩돼 있다.
⚠️ "예상 수익"은 새로 만든 숫자가 아니라, Freight의 road_cost.py가
   첫마일/막판마일 트럭 운임을 계산할 때 쓰는 estimate_drayage_fare()를
   그대로 재사용한 값이다 — 화주가 이미 낸 요금의 일부라는 뜻.
"""

from datetime import datetime

import streamlit as st

import shared_store
from rail_freight_nodes import MIN_CONSOLIDATION_TON
from road_cost import estimate_drayage_fare
from utils.data import DRIVER_CURRENT_STATION
from gemini_assist import explain_match

st.set_page_config(page_title="트럭기사용 앱", page_icon="🚚", layout="centered")

st.title("🚚 트럭기사용 앱")
st.caption("배차 안내 + 복귀 화물(공차 방지) 매칭 + 예상 수익")

if st.button("🔄 새로고침"):
    st.rerun()

driver = st.selectbox("기사님 성함", list(DRIVER_CURRENT_STATION.keys()))
my_station = DRIVER_CURRENT_STATION[driver]
st.info(f"📍 현재 위치: **{my_station}** (데모용 하드코딩 — 실제 GPS 연동 전)")

shipments = shared_store.read_shipments()
if not shipments:
    st.warning("현재 예약된 화물이 없습니다. 화주 예약이 들어오면 여기에 표시됩니다.")
    st.stop()

# ── 오늘의 배차: 내 현재 위치로 도착 예정인 화물 ──────────────
arriving = sorted(
    (s for s in shipments if s.get("도착화물역") == my_station and s.get("도착예정시각")),
    key=lambda s: s["도착예정시각"],
)

st.subheader(f"📦 {my_station} 도착 예정 화물")
if not arriving:
    st.caption("현재 이 역으로 도착 예정인 화물이 없습니다.")
else:
    for s in arriving:
        remaining_min = int((s["도착예정시각"] - datetime.now()).total_seconds() // 60)
        st.write(
            f"- **{s['화물ID']}** · {s.get('화물종류','-')} · {s.get('중량톤','-')}톤 "
            f"· 도착 {s['도착예정시각'].strftime('%H:%M')} ({'예정' if remaining_min >= 0 else '경과'} {abs(remaining_min)}분)"
        )

st.divider()
st.subheader("♻️ 복귀 화물 (공차 방지 매칭 · 예상 수익)")

candidates = [s for s in shipments if s.get("출발화물역") == my_station]

if not candidates:
    st.warning(f"{my_station} 출발 예정인 복귀 화물이 아직 없습니다.")
else:
    def _match_score(s: dict) -> float:
        weight = s.get("중량톤") or 0
        grouped = s.get("결합화주ID목록") or []
        weight_component = min(40.0, (weight / MIN_CONSOLIDATION_TON) * 40.0) if MIN_CONSOLIDATION_TON else 0
        grouped_component = 10.0 if grouped else 0.0
        return round(50.0 + weight_component + grouped_component, 1)

    def _expected_revenue(s: dict):
        distance = s.get("막판마일거리km")
        weight = s.get("중량톤")
        if distance is None or weight is None:
            return None
        return estimate_drayage_fare(distance, weight)

    @st.cache_data(show_spinner=False)
    def _cached_explain_match(score: float, shipment_id: str, factors: dict) -> str:
        # shipment_id는 캐시 키를 화물ID별로 구분하기 위한 용도일 뿐, 실제 인자는 factors
        return explain_match(score, factors)

    candidates_scored = []
    for s in candidates:
        score = _match_score(s)
        revenue = _expected_revenue(s)
        candidates_scored.append((s, score, revenue))
    candidates_scored.sort(key=lambda t: t[1], reverse=True)

    for s, score, revenue in candidates_scored:
        with st.container(border=True):
            c1, c2, c3 = st.columns([2, 1, 1])
            with c1:
                st.markdown(f"**{s['화물ID']}** · {s.get('화물종류','-')} → {s.get('도착지주소','-')}")
                st.caption(f"중량 {s.get('중량톤','-')}톤 · 목적화물역 {s.get('도착화물역','-')}")
            with c2:
                st.metric("결합적합도", f"{score}점")
                st.caption("✅ 공차 방지" if score >= 75 else "△ 검토 필요")
            with c3:
                if revenue is not None:
                    st.metric("예상 수익", f"{revenue:,}원")
                    st.caption("막판마일 운임 기준")
                else:
                    st.metric("예상 수익", "-")
                    st.caption("거리 정보 없음")

            factors = {
                "중량톤": s.get("중량톤"),
                "결합배송여부": bool(s.get("결합화주ID목록")),
                "결합최소기준톤": MIN_CONSOLIDATION_TON,
            }
            try:
                narrative = _cached_explain_match(score, s["화물ID"], factors)
                st.caption(f"🤖 {narrative}")
            except Exception:
                st.caption("AI 설명 생성 실패 — 위 결합적합도 점수와 근거 수치를 참고해 주세요.")

    st.caption(
        f"※ 결합적합도 = 50 + min(40, 중량톤/{MIN_CONSOLIDATION_TON}×40) + (묶음 배송이면 +10) "
        "— 학습 모델이 아닌 명시적 규칙 점수. 예상 수익은 road_cost.estimate_drayage_fare()로 "
        "계산한 실제 운임 함수값이며, 위 문장 설명만 AI(Gemini)가 생성합니다."
    )
