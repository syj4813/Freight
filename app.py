# -*- coding: utf-8 -*-
"""
소량 화물 운송수단 비교 플랫폼 (프로토타입)

화주가 화물 정보를 입력하면:
  1. 트럭 단독 / 퀵서비스 / KTX특송(규격 충족 시) / 철도 통합운송(가능 시)
     을 비교표로 제시
  2. 철도 통합운송은 가상 화주 풀(pool)과의 결합 가능 여부를 백그라운드에서
     판정하고, 화주에게는 결과 메시지만 노출
  3. 실시간 데이터(카카오맵 소요시간 등)와 추정치(화물열차 운임 등)를
     명확히 구분 표시
"""

from datetime import date, datetime, time, timedelta

import streamlit as st

from geocode import geocode_address
from road_cost import (
    get_road_distance_duration,
    estimate_truck_fare,
    estimate_quick_fare,
)
from rail_freight_nodes import CONTAINER_MAX_TON
from ktx_tucking import check_ktx_tucking_eligible, KTX_TUCKING_STATIONS
from consolidation import ShipperOrder, evaluate_consolidation
from emission import calculate_truck_vs_rail_savings, calculate_carbon_mileage
from cargo import classify_cargo_type, apply_surcharge, is_mode_restricted, CargoCategory
from gemini_assist import classify_cargo_category as gemini_classify_cargo
from gemini_assist import chat_fill_slots, CHAT_SLOT_KEYS
from intermodal import estimate_intermodal
from map_view import build_route_map

st.set_page_config(page_title="소량 화물 운송수단 비교", layout="wide")

MODE_ICONS = {
    "트럭 단독": "🚛",
    "퀵서비스": "🛵",
    "KTX특송": "🚄",
    "철도 통합운송": "🚆",
}


def _icon_for(label: str) -> str:
    for key, icon in MODE_ICONS.items():
        if label.startswith(key):
            return icon
    return "📦"

# ── API 키 주입 (Streamlit Secrets) ─────────────────────────────
import geocode as _geocode_mod
import road_cost as _road_cost_mod
import gemini_assist as _gemini_mod

_geocode_mod.GOOGLE_MAPS_API_KEY = st.secrets.get("GOOGLE_MAPS_API_KEY", "")
_road_cost_mod.KAKAO_REST_API_KEY = st.secrets.get("KAKAO_REST_API_KEY", "")
_gemini_mod.GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")  # Agent Platform Model APIs 키
# TODO: TAGO_API_KEY는 아직 어떤 모듈에서도 쓰지 않음 (여객열차 참고용 연동 시 활용 예정)
TAGO_API_KEY = st.secrets.get("TAGO_API_KEY", "")


# ── 데모용 가상 화주 풀 (실제 서비스라면 누적 주문 DB) ───────────
# ⚠️ 좌표는 앱 기본 데모 주소("서울 중구 세종대로"/"부산 동구 중앙대로")가
# 매칭되는 화물역(오봉역/부산진역)과 일치하도록 잡았습니다. 실제로는
# 화물역 좌표 자체와 무관하게 화주 위치 그대로 누적된 값이어야 합니다.
# 방향성이 있는 실제 물류 특성을 반영해 오봉→부산진, 부산진→오봉 양쪽
# 방향 샘플을 모두 넣어뒀습니다 (한쪽 방향만 있으면 반대 방향 화주는
# 항상 결합 실패로 나옵니다).
@st.cache_data
def get_mock_pool() -> list[ShipperOrder]:
    today = date.today()
    return [
        # 오봉역 -> 부산진역 방향
        ShipperOrder("P1", 37.42, 126.90, 35.13, 129.04, 6.0, today + timedelta(days=1)),
        ShipperOrder("P2", 37.43, 126.91, 35.13, 129.04, 5.5, today + timedelta(days=2)),
        ShipperOrder("P3", 37.42, 126.89, 35.13, 129.03, 4.0, today),
        # 부산진역 -> 오봉역 방향
        ShipperOrder("P4", 35.13, 129.04, 37.42, 126.90, 6.0, today + timedelta(days=1)),
        ShipperOrder("P5", 35.13, 129.03, 37.43, 126.91, 5.5, today + timedelta(days=2)),
        ShipperOrder("P6", 35.12, 129.04, 37.42, 126.89, 4.0, today),
    ]


st.title("소량 화물 운송수단 비교")
st.caption("트럭 · 퀵서비스 · KTX특송 · 철도 통합운송 비교 프로토타입")

# ── 챗봇 자동입력: 인터페이스 사용이 어려운 화주를 위한 자연어 입력 ──
_defaults = {
    "f_origin": "서울특별시 중구 세종대로",
    "f_dest": "부산광역시 동구 중앙대로",
    "f_cargo": "전자부품",
    "f_weight": 8.0,
    "f_date": date.today(),
}
for k, v in _defaults.items():
    st.session_state.setdefault(k, v)

with st.expander("💬 대화로 자동 입력하기 (인터페이스가 어려우신 분께 추천)", expanded=False):
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = [
            {"role": "assistant", "content": "안녕하세요! 화물 정보를 대화로 알려주시면 아래 입력폼을 자동으로 채워드릴게요. 출발지가 어디인가요?"}
        ]
    if "chat_known" not in st.session_state:
        st.session_state.chat_known = {k: None for k in CHAT_SLOT_KEYS}

    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    user_msg = st.chat_input("메시지를 입력하세요")
    if user_msg:
        st.session_state.chat_messages.append({"role": "user", "content": user_msg})
        conversation_text = "\n".join(
            f"{m['role']}: {m['content']}" for m in st.session_state.chat_messages
        )
        try:
            result = chat_fill_slots(conversation_text, st.session_state.chat_known)
            for k in CHAT_SLOT_KEYS:
                if result.get(k) not in (None, ""):
                    st.session_state.chat_known[k] = result[k]
            reply = result.get("assistant_reply", "죄송합니다, 다시 한 번 말씀해 주시겠어요?")
            st.session_state.chat_messages.append({"role": "assistant", "content": reply})

            # 파악된 값을 폼에 실시간 반영
            known = st.session_state.chat_known
            if known.get("origin"):
                st.session_state["f_origin"] = known["origin"]
            if known.get("destination"):
                st.session_state["f_dest"] = known["destination"]
            if known.get("cargo_type"):
                st.session_state["f_cargo"] = known["cargo_type"]
            if known.get("weight_kg"):
                st.session_state["f_weight"] = float(known["weight_kg"])
            if known.get("desired_date"):
                try:
                    st.session_state["f_date"] = datetime.strptime(
                        known["desired_date"], "%Y-%m-%d"
                    ).date()
                except ValueError:
                    pass
        except Exception as e:
            st.session_state.chat_messages.append(
                {"role": "assistant", "content": f"처리 중 오류가 발생했습니다: {e}"}
            )
        st.rerun()

    if st.button("대화 초기화", key="chat_reset"):
        del st.session_state["chat_messages"]
        del st.session_state["chat_known"]
        st.rerun()

with st.form("order_form"):
    col1, col2 = st.columns(2)
    with col1:
        origin_addr = st.text_input("출발지 주소", key="f_origin")
    with col2:
        dest_addr = st.text_input("도착지 주소", key="f_dest")

    col3, col4, col5 = st.columns(3)
    with col3:
        cargo_type = st.text_input("화물 종류", key="f_cargo")
    with col4:
        weight_kg = st.number_input("중량(kg)", min_value=0.1, key="f_weight")
    with col5:
        long_side_cm = st.number_input("최장변(cm)", min_value=1.0, value=40.0)

    desired_date = st.date_input("희망 발송일", key="f_date")
    desired_time = st.time_input("희망 출발시각", value=time(9, 0))
    submitted = st.form_submit_button("비교하기")

if submitted:
    with st.spinner("주소 확인 및 경로 계산 중..."):
        origin_coord = geocode_address(origin_addr)
        dest_coord = geocode_address(dest_addr)

    if not origin_coord or not dest_coord:
        st.error("주소를 확인할 수 없습니다. 정확한 주소를 입력해 주세요.")
        st.stop()

    origin_lat, origin_lng = origin_coord
    dest_lat, dest_lng = dest_coord
    weight_ton = weight_kg / 1000
    departure_dt = datetime.combine(desired_date, desired_time)

    def _eta(duration_min: float) -> str:
        """소요시간(분)을 희망 출발시각에 더해 도착예정시각 문자열로 변환.
        ⚠️ 실제 화물열차 시각표가 아니라 거리/평균속도 기반 추정 소요시간에
        근거한 예상치입니다."""
        arrival = departure_dt + timedelta(minutes=duration_min)
        return arrival.strftime("%m/%d %H:%M")

    cargo_category = classify_cargo_type(cargo_type)  # 기본값: 키워드 매칭
    try:
        cargo_category = CargoCategory(gemini_classify_cargo(cargo_type))
        classify_source = "Gemini 분류"
    except Exception as e:
        classify_source = "키워드 매칭 (Gemini 호출 실패로 폴백)"
        with st.expander("Gemini 호출 실패 상세 (디버그용)"):
            st.code(f"{type(e).__name__}: {e}")
    st.caption(f"분류된 화물 유형: {cargo_category.value} ({classify_source})")

    rows = []

    # ── 1) 트럭 단독 (기준) — 소요시간은 실시간, 요금은 추정치 ──
    try:
        road = get_road_distance_duration(origin_lng, origin_lat, dest_lng, dest_lat)
        truck_fare = apply_surcharge(estimate_truck_fare(road["distance_km"], weight_ton), cargo_category)
        emission_cmp = calculate_truck_vs_rail_savings(road["distance_km"], weight_ton)
        rows.append({
            "수단": "트럭 단독",
            "소요시간(분)": round(road["duration_min"]),
            "수령예상": _eta(road["duration_min"]),
            "요금(원)": truck_fare,
            "GWP(kgCO2eq)": emission_cmp["truck"]["gwp_kg_co2e"],
            "PM(kg)": emission_cmp["truck"]["pm_kg"],
            "데이터 성격": "시간: 실시간 / 요금·배출량: 추정치 (화물종류 할증 반영)",
        })
    except Exception as e:
        st.warning(f"카카오맵 API 호출 실패: {e} (API 키 확인 필요)")
        road = {"distance_km": 0, "duration_min": 0}
        emission_cmp = None

    # ── 2) 퀵서비스 (근거리·소형 한정, 위험물 등은 취급 불가) ──
    quick_fare = estimate_quick_fare(road["distance_km"], weight_kg)
    if quick_fare is not None and not is_mode_restricted(cargo_category, "퀵서비스"):
        rows.append({
            "수단": "퀵서비스",
            "소요시간(분)": round(road["duration_min"] * 0.8),  # 급행 가정, 추정
            "수령예상": _eta(road["duration_min"] * 0.8),
            "요금(원)": apply_surcharge(quick_fare, cargo_category),
            "데이터 성격": "추정치 (화물종류 할증 반영)",
        })
    elif quick_fare is not None:
        st.info(f"퀵서비스: {cargo_category.value} 화물은 취급 제한으로 비교에서 제외")

    # ── 3) KTX특송 (규격 충족 시만) ──
    # ⚠️ 데모 단순화: 실제로는 출발/도착 주소를 KTX특송 취급역으로 매핑하는
    # 로직이 필요합니다 (현재는 임의로 목록의 첫/끝 역을 사용).
    eligible, reason = check_ktx_tucking_eligible(
        KTX_TUCKING_STATIONS[0], KTX_TUCKING_STATIONS[-1],
        long_side_cm, long_side_cm * 2, weight_kg,
    )
    if eligible and not is_mode_restricted(cargo_category, "KTX특송"):
        rows.append({
            "수단": "KTX특송",
            "소요시간(분)": 240,  # 반나절 이내, 추정
            "수령예상": _eta(240),
            "요금(원)": "짐캐리 공시요금 확인 필요",
            "데이터 성격": "규격: 실제 기준 / 요금: 미확정(TODO)",
        })
    elif eligible:
        st.info(f"KTX특송: {cargo_category.value} 화물은 취급 제한으로 비교에서 제외")

    # ── 4) 철도 통합운송 — 첫마일(트럭)+철도+막판마일(트럭) door-to-door ──
    pool = get_mock_pool()
    new_order = ShipperOrder("NEW", origin_lat, origin_lng, dest_lat, dest_lng, weight_ton, desired_date)
    consolidation = evaluate_consolidation(new_order, pool)
    intermodal_result = None

    if consolidation.eligible:
        try:
            im = estimate_intermodal(
                origin_lat, origin_lng, dest_lat, dest_lng, weight_ton, departure_dt
            )
            intermodal_result = im
            mode_label = "전철화 구간" if im.electrified else "비전철(디젤) 구간"
            schedule_note = (
                f"실제 시각표 (열차번호 {im.train_no})" if im.schedule_source == "real"
                else "직행 열차 시각표 매칭 실패 → 거리/속도 기반 추정"
            )
            rows.append({
                "수단": f"철도 통합운송({mode_label})",
                "소요시간(분)": im.total_duration_min,
                "수령예상": im.arrival_dt.strftime("%m/%d %H:%M"),
                "요금(원)": apply_surcharge(im.total_fare_won, cargo_category),
                "GWP(kgCO2eq)": im.total_gwp_kg_co2e,
                "PM(kg)": im.total_pm_kg,
                "데이터 성격": (
                    f"소요시간: {schedule_note} / 요금: 추정치 "
                    f"({im.first_mile_km}km 트럭 + 철도 {im.rail_km}km + {im.last_mile_km}km 트럭)"
                ),
            })
            st.success(
                f"철도 이용 가능 ({consolidation.origin_node_name} → "
                f"{consolidation.dest_node_name}): {consolidation.reason}"
            )

            # ── 탄소 마일리지 강조 표시 ──
            if emission_cmp is not None:
                gwp_savings = emission_cmp["truck"]["gwp_kg_co2e"] - im.total_gwp_kg_co2e
                mileage = calculate_carbon_mileage(gwp_savings)
                mcol1, mcol2 = st.columns(2)
                mcol1.metric("탄소 절감량", f"{gwp_savings:.1f} kgCO2eq", "트럭 대비")
                mcol2.metric("탄소 마일리지", f"{mileage:,} P", "적립 예상")
                st.caption(
                    "※ 탄소 마일리지는 절감된 CO2 1kg당 10P로 환산한 시연용 지표입니다 "
                    "(실제 서비스 시 별도 제도 연동 및 전환 비율 재산정 필요)."
                )
        except Exception as e:
            st.warning(f"철도 구간 계산 실패: {e} (API 키 확인 필요)")
    else:
        node_info = (
            f" ({consolidation.origin_node_name} → {consolidation.dest_node_name})"
            if consolidation.origin_node_name
            else ""
        )
        st.info(f"철도 통합운송{node_info}: {consolidation.reason}")

    st.divider()
    st.subheader("🗺️ 이동경로")
    origin_node_tuple = (
        (intermodal_result.origin_node_lat, intermodal_result.origin_node_lng, intermodal_result.origin_node_name)
        if intermodal_result else None
    )
    dest_node_tuple = (
        (intermodal_result.dest_node_lat, intermodal_result.dest_node_lng, intermodal_result.dest_node_name)
        if intermodal_result else None
    )
    route_map = build_route_map(
        origin_lat, origin_lng, dest_lat, dest_lng,
        origin_node=origin_node_tuple, dest_node=dest_node_tuple,
    )
    st.pydeck_chart(route_map)
    legend_bits = ["🟠 트럭 직송"]
    if intermodal_result:
        legend_bits += ["🟢 첫마일/막판마일(트럭)", "🔵 철도 구간"]
    st.caption(" · ".join(legend_bits))

    st.subheader("비교 결과")

    if rows:
        numeric_fare_rows = [r for r in rows if isinstance(r["요금(원)"], (int, float))]
        cheapest = min(numeric_fare_rows, key=lambda r: r["요금(원)"])["수단"] if numeric_fare_rows else None
        fastest = min(rows, key=lambda r: r["소요시간(분)"])["수단"]
        greenest = min(
            (r for r in rows if "GWP(kgCO2eq)" in r), key=lambda r: r["GWP(kgCO2eq)"], default=None
        )
        greenest_label = greenest["수단"] if greenest else None

        cols = st.columns(len(rows))
        for col, row in zip(cols, rows):
            with col:
                with st.container(border=True):
                    st.markdown(f"### {_icon_for(row['수단'])} {row['수단']}")
                    badges = []
                    if row["수단"] == cheapest:
                        badges.append("💰 최저가")
                    if row["수단"] == fastest:
                        badges.append("⚡ 최단시간")
                    if row["수단"] == greenest_label:
                        badges.append("🌱 최저탄소")
                    if badges:
                        st.caption(" · ".join(badges))

                    fare_display = (
                        f"{row['요금(원)']:,}원"
                        if isinstance(row["요금(원)"], (int, float))
                        else row["요금(원)"]
                    )
                    st.metric("요금", fare_display)
                    st.metric("소요시간", f"{row['소요시간(분)']}분")
                    st.write(f"📅 수령예상: **{row.get('수령예상', '-')}**")
                    if "GWP(kgCO2eq)" in row:
                        st.write(f"🏭 GWP: {row['GWP(kgCO2eq)']} kgCO2eq")
                    st.caption(row["데이터 성격"])

        # ── 요금/시간 비교 막대 그래프 ──
        if numeric_fare_rows:
            st.write("")
            chart_col1, chart_col2 = st.columns(2)
            with chart_col1:
                st.caption("요금 비교 (원)")
                st.bar_chart({r["수단"]: r["요금(원)"] for r in numeric_fare_rows})
            with chart_col2:
                st.caption("소요시간 비교 (분)")
                st.bar_chart({r["수단"]: r["소요시간(분)"] for r in rows})

        with st.expander("상세 데이터 표로 보기"):
            st.table(rows)
    else:
        st.warning("비교 가능한 운송수단이 없습니다.")

    st.caption(
        "※ '추정치'로 표시된 항목은 공개 데이터가 없어 근사식으로 산출한 값입니다. "
        "실제 서비스 전환 시 코레일 화물 계약운임, 짐캐리 공시요금 등으로 교체가 필요합니다. "
        "수령예상시각은 실제 화물열차 시각표가 아닌 평균속도 기반 추정치입니다."
    )
