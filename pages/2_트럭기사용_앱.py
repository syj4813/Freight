# -*- coding: utf-8 -*-
"""트럭기사용 앱 — 배차 안내 + 복귀 화물(공차 방지) 매칭.

⚠️ "매칭점수"는 학습된 모델이 아니라 명시적 규칙(가중합) 기반 점수다.
   Freight의 consolidation.py가 쓰는 결합 최소기준(MIN_CONSOLIDATION_TON)을
   그대로 가져와 "이 화물이 결합운송 기준에 얼마나 가까운가"를 점수화한다.
   "AI 매칭"이라는 표현은 쓰지 않는다 — 실제로 AI가 아니기 때문.
"""

from datetime import datetime

import streamlit as st

import shared_store
from rail_freight_nodes import MIN_CONSOLIDATION_TON
from utils.data import DRIVER_NAMES

st.set_page_config(page_title="트럭기사용 앱", page_icon="🚚", layout="centered")

st.title("🚚 트럭기사용 앱")
st.caption("열차 도착 배차 안내 + 복귀 화물(공차 방지) 매칭")

if st.button("🔄 새로고침"):
    st.rerun()

driver = st.selectbox("기사님 성함", DRIVER_NAMES)

shipments = shared_store.read_shipments()
if not shipments:
    st.info("현재 배차 가능한 화물이 없습니다. 화주 예약이 들어오면 여기에 표시됩니다.")
    st.stop()

# ── 오늘의 배차 후보: 도착예정시각이 가장 이른 순 ────────────────
upcoming = sorted(
    (s for s in shipments if s.get("도착예정시각")),
    key=lambda s: s["도착예정시각"],
)

st.subheader(f"📍 {driver} 기사님, 오늘의 배차 후보")
pick_labels = [
    f"{s['화물ID']} · {s.get('도착화물역','-')} {s['도착예정시각'].strftime('%H:%M')} 도착"
    for s in upcoming
]
picked_idx = st.selectbox("담당할 배차를 선택하세요", range(len(upcoming)), format_func=lambda i: pick_labels[i])
task = upcoming[picked_idx]

remaining_min = int((task["도착예정시각"] - datetime.now()).total_seconds() // 60)
st.info(
    f"**{task.get('출발화물역','-')} → {task.get('도착화물역','-')}** "
    f"({'예정' if remaining_min >= 0 else '경과'} {abs(remaining_min)}분)\n\n"
    f"화물ID **{task['화물ID']}** · {task.get('화물종류','-')} · {task.get('중량톤','-')}톤"
)

st.divider()
st.subheader("♻️ 복귀 화물 (공차 방지 매칭)")

current_station = task.get("도착화물역")
candidates = [
    s for s in shipments
    if s["화물ID"] != task["화물ID"] and s.get("출발화물역") == current_station
]

if not candidates:
    st.warning(f"{current_station} 출발 예정인 복귀 화물이 아직 없습니다.")
else:
    def _match_score(s: dict) -> float:
        weight = s.get("중량톤") or 0
        grouped = s.get("결합화주ID목록") or []
        weight_component = min(40.0, (weight / MIN_CONSOLIDATION_TON) * 40.0) if MIN_CONSOLIDATION_TON else 0
        grouped_component = 10.0 if grouped else 0.0
        return round(50.0 + weight_component + grouped_component, 1)

    rows = []
    for s in candidates:
        score = _match_score(s)
        rows.append({
            "화물ID": s["화물ID"],
            "화물종류": s.get("화물종류", "-"),
            "목적지": s.get("도착화물역", "-"),
            "중량(톤)": s.get("중량톤", "-"),
            "결합적합도": score,
            "공차방지여부": "✅ 공차 방지" if score >= 75 else "△ 검토 필요",
        })
    rows.sort(key=lambda r: r["결합적합도"], reverse=True)
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.caption(
        f"※ 결합적합도 = 50 + min(40, 중량톤/{MIN_CONSOLIDATION_TON}×40) + (묶음 배송이면 +10). "
        "학습 모델이 아닌 명시적 규칙 점수이며, 소스는 consolidation.py의 결합 기준과 동일합니다."
    )
