# -*- coding: utf-8 -*-
"""화차 배치 추천 (관제센터 확장) — 서모게이트 ML 모델 기반.

⚠️ 이 페이지가 쓰는 예측 모델(car_assignment.py)은 사용자가 별도로 학습한
   실제 LightGBM 트리 앙상블을 파이썬으로 이식한 것입니다. 다만 학습에 쓰인
   정답 라벨은 실제 코레일 배치 결과가 아니라 자체 정의한 합성 규칙 기반
   라벨이고, 화차 편성 자체도 실제 데이터가 없어 열차번호 기반 mock으로
   생성합니다 — "모델은 진짜, 데이터는 데모"라는 한계를 화면에도 표시합니다.
"""

import streamlit as st

import shared_store
import car_assignment as ca

st.set_page_config(page_title="화차 배치 추천", page_icon="🚃", layout="wide")

st.title("🚃 화차 배치 추천")
st.caption("서모게이트 ML 모델(LightGBM, 150개 트리)로 화물에 맞는 화차를 추천합니다.")
st.warning(
    "⚠️ 예측 모델 자체는 실제 학습된 것이지만, 학습 라벨은 코레일 실제 배치 규정이 "
    "아닌 자체 정의 합성 데이터입니다. 화차 편성도 실제 편성 데이터가 없어 열차번호 "
    "기반으로 결정론적으로 생성한 mock입니다. 참고용으로만 활용하세요.",
    icon="⚠️",
)

if st.button("🔄 새로고침"):
    st.rerun()

shipments = shared_store.read_shipments()
pending = [s for s in shipments if s.get("열차번호") and not s.get("화차배정")]

if not pending:
    st.info("화차 배정이 필요한 예약이 없습니다. (철도 통합운송 예약 중 미배정 건만 표시)")
    st.stop()

labels = [f"{s['화물ID']} · {s.get('열차번호')} · {s.get('화물종류','-')} {s.get('중량톤','-')}톤" for s in pending]
idx = st.selectbox("배치할 화물을 선택하세요", range(len(pending)), format_func=lambda i: labels[i])
shipment = pending[idx]
train_no = shipment["열차번호"]

st.subheader(f"화물 {shipment['화물ID']} — 열차 {train_no} 편성")

total_cars = st.slider("편성 화차 수 (mock)", min_value=10, max_value=30, value=20)
cars = ca.generate_mock_train_composition(train_no, total_cars=total_cars)

with st.expander("편성 전체 보기 (mock)"):
    st.dataframe(
        [
            {
                "화차번호": c.car_index, "종류": c.car_type,
                "최대적재(kg)": c.max_load_kg, "현재적재(kg)": c.current_load_kg,
                "잔여용적(m³)": c.remaining_capacity_m3,
                "위험물차와거리": c.distance_from_hazmat_car, "위치": c.position,
            }
            for c in cars
        ],
        use_container_width=True, hide_index=True,
    )

cargo_weight_kg = shipment.get("화물중량kg") or (shipment.get("중량톤", 0) * 1000)
cargo_length_cm = shipment.get("화물길이cm") or 100.0
cargo_width_cm = shipment.get("화물폭cm") or 60.0
cargo_height_cm = shipment.get("화물높이cm") or 50.0
hazmat = bool(shipment.get("위험물여부"))
fragile = bool(shipment.get("파손주의여부"))

c1, c2, c3, c4 = st.columns(4)
c1.metric("중량", f"{cargo_weight_kg:,.0f} kg")
c2.metric("규격(길이×폭×높이)", f"{cargo_length_cm:.0f}×{cargo_width_cm:.0f}×{cargo_height_cm:.0f} cm")
c3.metric("위험물", "예" if hazmat else "아니오")
c4.metric("파손주의", "예" if fragile else "아니오")

recommendations = ca.recommend_cars(
    cargo_weight_kg, cargo_length_cm, cargo_width_cm, cargo_height_cm,
    hazmat, fragile, cars, top_n=5,
)

st.divider()
st.subheader("🤖 추천 순위 (적합도 점수)")

for rank, r in enumerate(recommendations, start=1):
    car = r["car"]
    with st.container(border=True):
        cc1, cc2, cc3 = st.columns([1, 2, 1])
        with cc1:
            st.metric(f"{rank}위", f"{r['score']*100:.1f}점")
        with cc2:
            st.markdown(f"**{car.car_index}번 화차** · {car.car_type} · {car.position}")
            st.caption(
                f"잔여적재 {car.max_load_kg - car.current_load_kg:,.0f}kg / "
                f"잔여용적 {car.remaining_capacity_m3}m³ · 위험물차와 {car.distance_from_hazmat_car}칸"
            )
        with cc3:
            if not r["capacity_ok"]:
                st.error("적재 초과")
            elif hazmat and car.distance_from_hazmat_car == 0:
                st.success("위험물차 본인")
            else:
                st.success("적재 가능")

best = recommendations[0]
if st.button(f"✅ {best['car'].car_index}번 화차로 배정 확정"):
    shared_store.assign_car(shipment["화물ID"], best["car"].car_index)
    st.success(f"{shipment['화물ID']} → {best['car'].car_index}번 화차 배정 완료")
    st.rerun()

st.caption(
    "※ 적합도 점수는 실제 학습된 모델(입력 대비 결정론적)이 계산하며, 화차 편성 자체는 "
    "mock입니다. '적재 가능/초과'는 모델 점수와 별개로 잔여 적재량을 직접 비교한 규칙 판정입니다."
)
