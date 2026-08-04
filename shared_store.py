# -*- coding: utf-8 -*-
"""
화주용 예약 확정(app.py) → 트럭기사 앱 / 관제센터가 참조하는 세션 간 공유 저장소.

st.cache_resource로 반환하는 객체는 세션(브라우저 탭)이 아니라 앱 프로세스
전체에서 싱글턴으로 공유된다. 별도 DB 없이 데모 수준의 "세션 간 데이터 공유"를
구현하기 위한 선택.

⚠️ 한계: Streamlit Cloud에서 앱이 유휴 상태로 슬립하거나 재배포되면 프로세스가
   재시작되면서 인메모리 데이터가 초기화된다 — 영속성이 필요하면 SQLite 파일이나
   외부 DB(Supabase 등)로 교체가 필요하다 (TODO, 데모 스코프에서는 보류).
⚠️ "실시간"은 웹소켓 push가 아니라 화면을 다시 그릴 때(rerun) 최신 상태를
   읽어오는 폴링 방식이다. 각 페이지에 새로고침 버튼을 뒀고, 자동 주기 갱신이
   필요하면 Streamlit 1.37+의 st.fragment(run_every=...)로 교체 가능 (TODO).
"""

import uuid
from datetime import datetime
from threading import Lock

import streamlit as st

# 화주 door-to-door 여정의 8단계 — 예약시각~도착예정시각 사이 경과 비율로
# 결정론적으로 계산한다 (random 사용 안 함).
STAGE_LABELS = [
    "화주 공장 출발",
    "육상 트럭 이동중 (첫마일)",
    "화물역(CY) 도착",
    "철도 상차 대기",
    "철도 운송중",
    "목적지 화물역 도착",
    "육상 트럭 배송중 (막판마일)",
    "최종 목적지 도착",
]


@st.cache_resource
def _get_store():
    return {"shipments": {}, "lock": Lock()}


def add_shipment(**fields) -> str:
    """예약 확정 시 화물 1건을 스토어에 기록하고 화물ID를 반환.

    필수로 기대하는 키(app.py 쪽에서 채워 넣음):
      화물종류, 출발지주소, 도착지주소, 출발화물역, 도착화물역, 중량톤,
      예약시각, 희망출발시각, 도착예정시각, 요금원,
      GWP(kgCO2eq), GWP절감(kgCO2eq대비트럭), 결합화주ID목록, 열차번호, 시각표출처
    """
    store = _get_store()
    shipment_id = fields.pop("화물ID", None) or f"KRL-{uuid.uuid4().hex[:8].upper()}"
    record = {"화물ID": shipment_id, **fields}
    with store["lock"]:
        store["shipments"][shipment_id] = record
    return shipment_id


def read_shipments() -> list[dict]:
    """전체 예약 목록 조회 (최신 등록순)."""
    store = _get_store()
    with store["lock"]:
        rows = list(store["shipments"].values())
    return sorted(rows, key=lambda r: r.get("예약시각") or datetime.min, reverse=True)


def get_shipment(shipment_id: str) -> dict | None:
    store = _get_store()
    with store["lock"]:
        return store["shipments"].get(shipment_id)


def current_stage_idx(record: dict) -> int:
    """예약시각 대비 도착예정시각까지의 경과 비율로 8단계 중 인덱스를 계산.

    random 대신 실제 타임스탬프 기반 결정론적 계산 — 다만 이것도 여전히
    "화물이 정말 그 단계에 있다"는 실측치는 아니라 시간 흐름을 선형 근사한
    시뮬레이션이라는 한계가 있다 (실제 GPS/RFID 연동 전까지는 불가피).
    """
    now = datetime.now()
    start = record.get("예약시각")
    eta = record.get("도착예정시각")
    if not start or not eta or eta <= start:
        return 0
    ratio = (now - start).total_seconds() / (eta - start).total_seconds()
    ratio = min(max(ratio, 0.0), 0.999)
    return min(int(ratio * len(STAGE_LABELS)), len(STAGE_LABELS) - 1)
