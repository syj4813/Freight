# -*- coding: utf-8 -*-
"""관제센터 — 전체 예약 현황 및 KPI.

⚠️ 개별 트럭/화차의 실시간 GPS 좌표는 실제 텔레매틱스 연동 없이는 만들어낼
   근거가 없어(예전처럼 무작위 좌표를 찍는 대신) 넣지 않았다. 대신 화물역별
   예약 건수를 집계해서 보여준다 — 개별 차량 위치 대신 "어디에 물동량이
   몰려 있는가"는 실측 데이터로 답할 수 있는 질문이기 때문.
"""

from collections import Counter

import plotly.graph_objects as go
import streamlit as st

import shared_store
from utils.data import STATIONS

st.set_page_config(page_title="관제센터", page_icon="🛰️", layout="wide")

st.title("🛰️ 관제센터")
st.caption("전체 예약 현황과 핵심 KPI를 실측 데이터 기준으로 집계합니다.")

if st.button("🔄 새로고침"):
    st.rerun()

shipments = shared_store.read_shipments()

total_count = len(shipments)
gwp_values = [s.get("GWP절감(kgCO2eq대비트럭)") for s in shipments if s.get("GWP절감(kgCO2eq대비트럭)") is not None]
total_gwp_savings = sum(gwp_values)
grouped_count = sum(1 for s in shipments if s.get("결합화주ID목록"))
lead_times_min = [
    (s["도착예정시각"] - s["예약시각"]).total_seconds() / 60
    for s in shipments
    if s.get("도착예정시각") and s.get("예약시각")
]
avg_lead_time = sum(lead_times_min) / len(lead_times_min) if lead_times_min else 0

top1, top2, top3, top4 = st.columns(4)
top1.metric("총 예약 건수", f"{total_count}건")
top2.metric("묶음(결합) 배송 건수", f"{grouped_count}건", f"{round(grouped_count/total_count*100,1) if total_count else 0}%")
top3.metric("탄소절감 합계", f"{total_gwp_savings:.1f} kgCO2eq")
top4.metric("평균 리드타임", f"{avg_lead_time:.0f}분" if lead_times_min else "-")

st.divider()

left, right = st.columns([1.4, 1])

with left:
    st.subheader("화물역별 예약 건수")
    station_counts = Counter()
    for s in shipments:
        if s.get("출발화물역"):
            station_counts[s["출발화물역"]] += 1
        if s.get("도착화물역"):
            station_counts[s["도착화물역"]] += 1

    fig = go.Figure()
    lats = [v[0] for v in STATIONS.values()]
    lons = [v[1] for v in STATIONS.values()]
    names = list(STATIONS.keys())
    sizes = [12 + station_counts.get(n, 0) * 6 for n in names]
    fig.add_trace(go.Scattermapbox(
        lat=lats, lon=lons, mode="markers+text",
        marker=dict(size=sizes, color="#00376b"),
        text=[f"{n} ({station_counts.get(n,0)}건)" for n in names],
        textposition="top center",
    ))
    fig.update_layout(
        mapbox=dict(style="carto-positron", zoom=5.6, center=dict(lat=36.3, lon=127.8)),
        margin=dict(l=0, r=0, t=0, b=0), height=460,
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption("마커 크기 = 해당 역이 출발/도착화물역으로 걸린 예약 건수 (실측)")

with right:
    st.subheader("예약 목록")
    if shipments:
        table_rows = [
            {
                "화물ID": s["화물ID"],
                "구간": f"{s.get('출발화물역','-')}→{s.get('도착화물역','-')}",
                "중량(톤)": s.get("중량톤", "-"),
                "결합": "O" if s.get("결합화주ID목록") else "-",
            }
            for s in shipments
        ]
        st.dataframe(table_rows, use_container_width=True, hide_index=True)
    else:
        st.info("아직 예약된 화물이 없습니다.")

st.caption(
    "※ 개별 트럭·화차의 실시간 위치는 실제 GPS/텔레매틱스 연동이 없어 표시하지 않습니다. "
    "위 지표는 전부 shared_store에 실제로 쌓인 예약 데이터를 집계한 값입니다."
)
