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

import glob
from datetime import datetime, time, timedelta

import streamlit as st

from geocode import geocode_address, geocode_to_formatted_address
from road_cost import (
    get_road_distance_duration,
    estimate_truck_fare,
    estimate_quick_fare,
    select_truck_tier,
)
from rail_freight_nodes import CONTAINER_MAX_TON
from ktx_tucking import check_ktx_tucking_eligible, KTX_TUCKING_STATIONS
from consolidation import ShipperOrder, evaluate_consolidation
from emission import calculate_truck_vs_rail_savings, calculate_carbon_mileage, calculate_tree_equivalent
from cargo import classify_cargo_type, apply_surcharge, is_mode_restricted, CargoCategory
from gemini_assist import classify_cargo_category as gemini_classify_cargo
from gemini_assist import parse_free_text_order, explain_comparison, explain_carbon_savings
from intermodal import estimate_intermodal
from map_view import build_route_map
from tz_utils import today_kst
import shared_store

st.set_page_config(page_title="소량 화물 운송수단 비교", layout="wide")

MODE_ICONS = {
    "트럭 단독": "🚛",
    "퀵서비스": "🛵",
    "KTX특송": "🚄",
    "철도 통합운송": "🚆",
}

# ── API 호출 캐시 래퍼 ───────────────────────────────────────────
# "예약 확정" 버튼처럼 폼 밖의 위젯을 눌러도 이 파일 전체가 다시 실행되는데
# (아래 "비교 결과 화면 유지" 참고), 매번 같은 입력으로 카카오맵/제미나이
# API를 다시 호출하면 느리고 비용이 든다. 입력이 그대로면 캐시로 즉시
# 반환되게 감싼다.
@st.cache_data(show_spinner=False)
def _cached_geocode(addr: str):
    return geocode_address(addr)


@st.cache_data(show_spinner=False)
def _cached_road_distance(origin_lng, origin_lat, dest_lng, dest_lat):
    return get_road_distance_duration(origin_lng, origin_lat, dest_lng, dest_lat)


@st.cache_data(show_spinner=False)
def _cached_gemini_classify(cargo_type_text: str):
    return gemini_classify_cargo(cargo_type_text)


@st.cache_data(show_spinner=False)
def _cached_intermodal(origin_lat, origin_lng, dest_lat, dest_lng, weight_ton, departure_dt):
    return estimate_intermodal(origin_lat, origin_lng, dest_lat, dest_lng, weight_ton, departure_dt)



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
#
# 2026-08-07 XROIS 일별화물운송실적(2023~2025, 81,687건) 집계 기준으로
# 노선별 비중을 실제에 맞게 조정함:
#   오봉↔부산진: 3년간 1,759건 (압도적 1위 — 이 풀에서도 가장 두껍게 유지)
#   오봉↔의왕: 422건 (소량이지만 꾸준)
#   오봉↔순천/천안: 각 17~21건 (드묾, 대표 사례로 1건씩만 유지)
#   오봉↔포항: 3년간 실적 0건 — 이번에 제거함 (이전엔 근거 없이 넣어뒀던 항목)
@st.cache_data
def get_mock_pool() -> list[ShipperOrder]:
    today = today_kst()
    return [
        # 오봉역 <-> 부산진역 (실제 최다 물동량 노선)
        ShipperOrder("P1", 37.42, 126.90, 35.13, 129.04, 6.0, today + timedelta(days=1)),
        ShipperOrder("P2", 37.43, 126.91, 35.13, 129.04, 5.5, today + timedelta(days=2)),
        ShipperOrder("P3", 37.42, 126.89, 35.13, 129.03, 4.0, today),
        ShipperOrder("P4", 35.13, 129.04, 37.42, 126.90, 6.0, today + timedelta(days=1)),
        ShipperOrder("P5", 35.13, 129.03, 37.43, 126.91, 5.5, today + timedelta(days=2)),
        ShipperOrder("P6", 35.12, 129.04, 37.42, 126.89, 4.0, today),
        # 오봉역 <-> 의왕역 (실제로도 소량이지만 꾸준한 노선)
        ShipperOrder("P7", 37.42, 126.90, 37.33, 126.97, 3.0, today + timedelta(days=1)),
        ShipperOrder("P8", 37.33, 126.97, 37.43, 126.91, 3.5, today),
        # 오봉역 <-> 순천역 (3년간 21건 — 드문 대표 사례 1건만 유지)
        ShipperOrder("P9", 37.42, 126.90, 34.95, 127.49, 5.0, today + timedelta(days=1)),
        # 오봉역 <-> 천안역 (3년간 17건 — 드문 대표 사례 1건만 유지)
        ShipperOrder("P10", 36.81, 127.14, 37.43, 126.91, 4.0, today),
    ]


st.title("소량 화물 운송수단 비교")
st.caption("트럭 · 퀵서비스 · KTX특송 · 철도 통합운송 비교 프로토타입")

# ── 자동입력: 인터페이스 사용이 어려운 화주를 위한 자연어 입력 ──
_defaults = {
    "f_origin": "서울특별시 중구 세종대로",
    "f_dest": "부산광역시 동구 중앙대로",
    "f_cargo": "전자부품",
    "f_weight": 8.0,
    "f_size": 40.0,
    "f_date": today_kst(),
    "f_time": time(9, 0),
}
for k, v in _defaults.items():
    st.session_state.setdefault(k, v)

AUTOFILL_EXAMPLES = [
    "부산에서 서울로 냉동식품 500kg 내일까지 보내야 해요",
    "천안에서 순천으로 전자부품 800kg, 최장변 60cm, 모레 오전 10시 출발이요",
    "포항에서 오봉으로 위험물 2톤 최대한 빨리 보내주세요",
]

with st.expander("💬 말로 설명하면 자동으로 입력해드립니다", expanded=False):
    st.caption("예시: " + " / ".join(f'"{ex}"' for ex in AUTOFILL_EXAMPLES))
    free_text = st.text_area(
        "화물 내용을 문장으로 입력하세요",
        placeholder=AUTOFILL_EXAMPLES[0],
        key="free_text_input",
    )
    if st.button("자동 입력"):
        if not free_text.strip():
            st.warning("먼저 화물 내용을 문장으로 입력해 주세요.")
        else:
            with st.spinner("입력 내용을 분석하는 중..."):
                try:
                    parsed = parse_free_text_order(free_text)
                except Exception as e:
                    parsed = None
                    st.error(f"입력을 이해하지 못했습니다 ({e}). 예시를 참고해서 다시 입력해 주세요.")

            if parsed is not None:
                # 파악된 항목은 즉시 폼에 반영 (출발지/도착지는 정확한 주소로 정규화)
                if parsed.get("origin"):
                    try:
                        resolved = geocode_to_formatted_address(parsed["origin"])
                    except Exception:
                        resolved = None
                    st.session_state["f_origin"] = resolved or parsed["origin"]
                if parsed.get("destination"):
                    try:
                        resolved = geocode_to_formatted_address(parsed["destination"])
                    except Exception:
                        resolved = None
                    st.session_state["f_dest"] = resolved or parsed["destination"]
                if parsed.get("cargo_type"):
                    st.session_state["f_cargo"] = parsed["cargo_type"]
                if parsed.get("weight_kg"):
                    st.session_state["f_weight"] = float(parsed["weight_kg"])
                if parsed.get("long_side_cm"):
                    st.session_state["f_size"] = float(parsed["long_side_cm"])
                if parsed.get("desired_date"):
                    try:
                        st.session_state["f_date"] = datetime.strptime(
                            parsed["desired_date"], "%Y-%m-%d"
                        ).date()
                    except ValueError:
                        pass
                if parsed.get("desired_time"):
                    try:
                        st.session_state["f_time"] = datetime.strptime(
                            parsed["desired_time"], "%H:%M"
                        ).time()
                    except ValueError:
                        pass

                # ── 재질문 로직: 필수 항목(출발지/도착지/중량) 누락 시 안내 ──
                missing = parsed.get("missing_fields") or []
                unset_optional = parsed.get("unset_optional_fields") or []
                OPTIONAL_LABELS = {
                    "cargo_type": "화물종류", "long_side_cm": "최장변",
                    "desired_date": "희망 발송일", "desired_time": "희망 출발시각",
                }
                if missing:
                    msg = parsed.get("clarification_message") or (
                        "다음 정보를 확인하지 못했습니다: " + ", ".join(missing)
                    )
                    st.warning(f"⚠️ {msg} 파악된 내용은 아래 폼에 반영했으니, 나머지를 문장에 추가해서 다시 입력해 주세요.")
                else:
                    st.success("아래 입력폼에 자동으로 채워넣었습니다. 확인 후 '비교하기'를 눌러주세요.")
                    if unset_optional:
                        labels = ", ".join(OPTIONAL_LABELS.get(f, f) for f in unset_optional)
                        st.info(f"ℹ️ {labels}은(는) 문장에 없어 기본값으로 채워졌습니다 — 폼에서 직접 확인·수정해 주세요.")

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
        long_side_cm = st.number_input("최장변(cm)", min_value=1.0, key="f_size")

    desired_date = st.date_input("희망 발송일", key="f_date")
    desired_time = st.time_input("희망 출발시각", key="f_time")
    submitted = st.form_submit_button("비교하기")

if submitted:
    # "비교하기"를 누른 이 실행에서만 True가 되는 submitted 값 그대로 아래
    # 블록의 조건으로 쓰면, 블록 안의 "예약 확정" 버튼을 누르는 순간 다시
    # 실행되는 스크립트에서는 submitted가 다시 False가 되어(폼을 다시
    # 제출한 게 아니므로) 이 블록 전체가 사라지고 예약 확정 클릭 자체가
    # 무시된다. session_state 플래그로 "결과 화면을 계속 보여줄지"를 별도로
    # 유지해서, 블록 내부의 버튼들이 눌려도 화면이 사라지지 않게 한다.
    st.session_state["show_comparison"] = True

if st.session_state.get("show_comparison"):
    with st.spinner("주소 확인 및 경로 계산 중..."):
        origin_coord = _cached_geocode(origin_addr)
        dest_coord = _cached_geocode(dest_addr)

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
        cargo_category = CargoCategory(_cached_gemini_classify(cargo_type))
        classify_source = "Gemini 분류"
    except Exception as e:
        classify_source = "키워드 매칭 (Gemini 호출 실패로 폴백)"
        with st.expander("Gemini 호출 실패 상세 (디버그용)"):
            st.code(f"{type(e).__name__}: {e}")
    st.caption(f"분류된 화물 유형: {cargo_category.value} ({classify_source})")

    rows = []

    # ── 1) 트럭 단독 (기준) — 소요시간은 실시간, 요금은 추정치 ──
    try:
        road = _cached_road_distance(origin_lng, origin_lat, dest_lng, dest_lat)
        truck_tier = select_truck_tier(weight_ton)
        truck_fare = apply_surcharge(estimate_truck_fare(road["distance_km"], weight_ton), cargo_category)
        emission_cmp = calculate_truck_vs_rail_savings(road["distance_km"], weight_ton)
        rows.append({
            "수단": "트럭 단독",
            "소요시간(분)": round(road["duration_min"]),
            "수령예상": _eta(road["duration_min"]),
            "요금(원)": truck_fare,
            "GWP(kgCO2eq)": emission_cmp["truck"]["gwp_kg_co2e"],
            "PM(kg)": emission_cmp["truck"]["pm_kg"],
            "데이터 성격": f"시간: 실시간 / 요금·배출량: 추정치 ({truck_tier.label} 차급, 화물종류 할증 반영)",
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
            im = _cached_intermodal(
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
                tree_equivalent = calculate_tree_equivalent(gwp_savings)
                mcol1, mcol2 = st.columns(2)
                mcol1.metric("탄소 절감량", f"{gwp_savings:.1f} kgCO2eq", "트럭 대비")
                mcol2.metric("탄소 마일리지", f"{mileage:,} P", "적립 예상")
                try:
                    narrative = explain_carbon_savings(gwp_savings, mileage, tree_equivalent)
                    st.info(f"🌱 {narrative}")
                except Exception:
                    st.info(f"🌱 나무 약 {tree_equivalent}그루의 연간 CO2 흡수량과 비슷한 양을 절감했습니다.")
                st.caption(
                    "※ 탄소 마일리지는 절감된 CO2 1kg당 10P로 환산한 시연용 지표이며, "
                    "나무 환산은 통상 인용되는 근사치(1그루당 연 21kg 흡수 가정)입니다 "
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
        truck_only_path=road.get("path"),
        origin_node=origin_node_tuple, dest_node=dest_node_tuple,
        first_mile_path=intermodal_result.first_mile_path if intermodal_result else None,
        last_mile_path=intermodal_result.last_mile_path if intermodal_result else None,
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

        # ── AI 요약 추천 ──
        st.write("")
        with st.container(border=True):
            st.markdown("#### 🤖 AI 요약")
            try:
                summary = explain_comparison(rows, consolidation.reason)
                st.write(summary)
            except Exception as e:
                st.caption(f"AI 요약을 생성하지 못했습니다 ({e}). 위 비교표를 참고해 주세요.")

        with st.expander("상세 데이터 표로 보기"):
            st.table(rows)

        # ── 예약 확정 → 공유 저장소 기록 ──────────────────────────
        # 실시간 Door-to-Door 추적·트럭기사 앱·관제센터 연계는 "철도 통합운송"
        # 예약 건에 한정한다. 트럭 단독/퀵서비스/KTX특송은 화물역(CY) 환적
        # 스테이지 자체가 없어 아래 후단 화면들의 데이터 모델과 맞지 않는다.
        st.divider()
        st.subheader("예약 확정")
        rail_row = next((r for r in rows if r["수단"].startswith("철도 통합운송")), None)

        if rail_row and consolidation.eligible and intermodal_result is not None:
            chosen_label = st.selectbox(
                "예약할 운송수단을 선택하세요",
                [r["수단"] for r in rows],
                index=[r["수단"] for r in rows].index(rail_row["수단"]),
            )
            if chosen_label == rail_row["수단"]:
                if st.button("✅ 예약 확정 (Door-to-Door 추적 시작)"):
                    gwp_savings = (
                        emission_cmp["truck"]["gwp_kg_co2e"] - intermodal_result.total_gwp_kg_co2e
                        if emission_cmp is not None else None
                    )
                    shipment_id = shared_store.add_shipment(
                        화물종류=cargo_type,
                        출발지주소=origin_addr,
                        도착지주소=dest_addr,
                        출발화물역=consolidation.origin_node_name,
                        도착화물역=consolidation.dest_node_name,
                        중량톤=weight_ton,
                        예약시각=datetime.now(),
                        희망출발시각=departure_dt,
                        도착예정시각=intermodal_result.arrival_dt,
                        요금원=rail_row["요금(원)"],
                        **{
                            "GWP(kgCO2eq)": rail_row.get("GWP(kgCO2eq)"),
                            "GWP절감(kgCO2eq대비트럭)": gwp_savings,
                        },
                        결합화주ID목록=consolidation.grouped_order_ids,
                        열차번호=getattr(intermodal_result, "train_no", None),
                        시각표출처=intermodal_result.schedule_source,
                        첫마일완료시각=intermodal_result.station_ready_dt,
                        철도출발시각=intermodal_result.rail_departure_dt,
                        철도도착시각=intermodal_result.rail_arrival_dt,
                        막판마일시작시각=intermodal_result.station_release_dt,
                        첫마일거리km=intermodal_result.first_mile_km,
                        막판마일거리km=intermodal_result.last_mile_km,
                        # ── 화차 배치 추천용 (아래 필드는 폼에서 직접 안 받고 근사) ──
                        # 화주가 입력하는 건 최장변(long_side_cm) 하나뿐이라, 폭/높이는
                        # 실측이 아니라 통상적인 화물 비율로 근사한 값입니다.
                        화물중량kg=weight_ton * 1000,
                        화물길이cm=long_side_cm,
                        화물폭cm=round(long_side_cm * 0.6, 1),
                        화물높이cm=round(long_side_cm * 0.5, 1),
                        위험물여부=(cargo_category == CargoCategory.HAZARDOUS),
                        파손주의여부=(cargo_category == CargoCategory.FRAGILE_HIGH_VALUE),
                        화차배정=None,
                    )
                    st.session_state["last_shipment_id"] = shipment_id
                    st.success(
                        f"예약이 확정되었습니다. 화물ID **{shipment_id}** — "
                        "왼쪽 페이지 목록의 '화주용 실시간추적'에서 진행 상황을 확인하세요."
                    )
            else:
                st.caption(
                    f"'{chosen_label}'은(는) 화물역 환적 구간이 없어 "
                    "실시간 추적·트럭기사 연계 대상이 아닙니다. 이 창에서는 예약을 기록하지 않습니다."
                )
        else:
            st.caption("※ 철도 통합운송이 가능한 건에 한해 예약 확정 및 실시간 추적을 제공합니다.")
    else:
        st.warning("비교 가능한 운송수단이 없습니다.")

    st.caption(
        "※ '추정치'로 표시된 항목은 공개 데이터가 없어 근사식으로 산출한 값입니다. "
        "실제 서비스 전환 시 코레일 화물 계약운임, 짐캐리 공시요금 등으로 교체가 필요합니다. "
        "수령예상시각은 실제 화물열차 시각표가 아닌 평균속도 기반 추정치입니다."
    )

st.divider()
st.subheader("후단 서비스 바로가기")


def _resolve_page(order_prefix: str) -> str | None:
    """pages/ 폴더에서 실제 파일을 찾아 경로를 반환.

    ⚠️ 코드에 한글 경로를 문자열로 직접 박아두면, macOS에서 git이 파일명을
    유니코드 정규화(NFC/NFD)하는 방식에 따라 실제 디스크상의 바이트열과
    코드 속 문자열이 달라 st.page_link()가 "파일을 못 찾음" 에러를 내는
    경우가 있다. glob으로 실행 시점에 실제 경로를 찾아 쓰면 이 문제를
    피할 수 있다.
    """
    matches = sorted(glob.glob(f"pages/{order_prefix}_*.py"))
    return matches[0] if matches else None


nav1, nav2, nav3, nav4 = st.columns(4)
with nav1:
    st.markdown("#### 📦 화주용 실시간추적")
    st.caption("예약된 화물의 door-to-door 진행 상황 추적")
    page = _resolve_page("1")
    if page:
        st.page_link(page, label="열기 →", icon="📦")
with nav2:
    st.markdown("#### 🚚 트럭기사용 앱")
    st.caption("배차 안내, 공차 방지 복귀화물 매칭")
    page = _resolve_page("2")
    if page:
        st.page_link(page, label="열기 →", icon="🚚")
with nav3:
    st.markdown("#### 🛰️ 관제센터")
    st.caption("전체 예약 현황, 탄소절감·리드타임 KPI")
    page = _resolve_page("3")
    if page:
        st.page_link(page, label="열기 →", icon="🛰️")
with nav4:
    st.markdown("#### 🚃 화차 배치 추천")
    st.caption("서모게이트 ML 모델로 화물-화차 매칭")
    page = _resolve_page("4")
    if page:
        st.page_link(page, label="열기 →", icon="🚃")
