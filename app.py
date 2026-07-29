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

from datetime import date, timedelta

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
from intermodal import estimate_intermodal

st.set_page_config(page_title="소량 화물 운송수단 비교", layout="centered")

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
@st.cache_data
def get_mock_pool() -> list[ShipperOrder]:
    today = date.today()
    return [
        ShipperOrder("P1", 37.42, 126.90, 35.13, 129.04, 6.0, today + timedelta(days=1)),
        ShipperOrder("P2", 37.43, 126.91, 35.13, 129.04, 5.5, today + timedelta(days=2)),
        ShipperOrder("P3", 37.42, 126.89, 35.13, 129.03, 4.0, today),
    ]


st.title("소량 화물 운송수단 비교")
st.caption("트럭 · 퀵서비스 · KTX특송 · 철도 통합운송 비교 프로토타입")

with st.form("order_form"):
    col1, col2 = st.columns(2)
    with col1:
        origin_addr = st.text_input("출발지 주소", "서울특별시 중구 세종대로")
    with col2:
        dest_addr = st.text_input("도착지 주소", "부산광역시 동구 중앙대로")

    col3, col4, col5 = st.columns(3)
    with col3:
        cargo_type = st.text_input("화물 종류", "전자부품")
    with col4:
        weight_kg = st.number_input("중량(kg)", min_value=0.1, value=8.0)
    with col5:
        long_side_cm = st.number_input("최장변(cm)", min_value=1.0, value=40.0)

    desired_date = st.date_input("희망 발송일", value=date.today())
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
            "요금(원)": "짐캐리 공시요금 확인 필요",
            "데이터 성격": "규격: 실제 기준 / 요금: 미확정(TODO)",
        })
    elif eligible:
        st.info(f"KTX특송: {cargo_category.value} 화물은 취급 제한으로 비교에서 제외")

    # ── 4) 철도 통합운송 — 첫마일(트럭)+철도+막판마일(트럭) door-to-door ──
    pool = get_mock_pool()
    new_order = ShipperOrder("NEW", origin_lat, origin_lng, dest_lat, dest_lng, weight_ton, desired_date)
    consolidation = evaluate_consolidation(new_order, pool)

    if consolidation.eligible:
        try:
            im = estimate_intermodal(origin_lat, origin_lng, dest_lat, dest_lng, weight_ton)
            mode_label = "전철화 구간" if im.electrified else "비전철(디젤) 구간"
            rows.append({
                "수단": f"철도 통합운송({mode_label})",
                "소요시간(분)": im.total_duration_min,
                "요금(원)": apply_surcharge(im.total_fare_won, cargo_category),
                "GWP(kgCO2eq)": im.total_gwp_kg_co2e,
                "PM(kg)": im.total_pm_kg,
                "데이터 성격": (
                    "첫마일/막판마일 트럭 구간 포함 door-to-door 추정치 "
                    f"({im.first_mile_km}km + 철도 {im.rail_km}km + {im.last_mile_km}km)"
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

    st.subheader("비교 결과")
    st.table(rows)

    st.caption(
        "※ '추정치'로 표시된 항목은 공개 데이터가 없어 근사식으로 산출한 값입니다. "
        "실제 서비스 전환 시 코레일 화물 계약운임, 짐캐리 공시요금 등으로 교체가 필요합니다."
    )
