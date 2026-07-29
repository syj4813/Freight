# -*- coding: utf-8 -*-
"""
트럭/퀵서비스 소요시간 및 요금 계산.

- 소요시간: 카카오맵 API 실제 데이터 (근사 아님)
- 요금: 국토부 화물 표준운임 가이드라인 취지를 참고한 거리+중량 근사식
        (특정 사설 업체 요금표가 아닌, 공적 참고 기준을 쓰는 이유는
         "왜 이 값이냐"는 질문에 근거를 댈 수 있어야 하기 때문)

⚠️ FARE_BASE_WON, FARE_PER_KM_WON, FARE_PER_TON_WON은 예시 계수입니다.
   제출 전 국토부 화물 표준운임 공고 자료로 실제 계수를 보정해야 합니다.
"""

import requests

KAKAO_REST_API_KEY = ""  # TODO: Streamlit secrets 등으로 주입

# 근사 요금 계수 (예시치, TODO: 보정 필요)
TRUCK_FARE_BASE_WON = 50_000
TRUCK_FARE_PER_KM_WON = 700
TRUCK_FARE_PER_TON_WON = 15_000

QUICK_FARE_BASE_WON = 15_000
QUICK_FARE_PER_KM_WON = 1_200  # 퀵은 근거리 급행이라 km당 단가가 더 높음
QUICK_MAX_WEIGHT_KG = 30  # 퀵서비스는 대개 소형화물 한정

# 첫마일/막판마일(출발지↔화물역, 화물역↔도착지) 근거리 운송 — 장거리 트럭과
# 달리 기본료가 낮음(단거리 배차이므로). km당/톤당 단가는 장거리와 동일하게
# 재사용. ⚠️ 추정치.
DRAYAGE_BASE_WON = 20_000


def get_road_distance_duration(
    origin_lng: float,
    origin_lat: float,
    dest_lng: float,
    dest_lat: float,
) -> dict:
    """카카오 모빌리티 API로 실제 도로 거리(m)/시간(초)/경로 좌표 조회.

    'path'는 지도에 실제 도로를 따라 그리기 위한 [(lat, lng), ...] 목록.
    API 응답의 sections[].roads[].vertexes는 [lng, lat, lng, lat, ...]
    형태로 평탄화돼 있어, 2개씩 끊어서 (lat, lng) 튜플로 변환한다.
    """
    url = "https://apis-navi.kakaomobility.com/v1/directions"
    headers = {"Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"}
    params = {
        "origin": f"{origin_lng},{origin_lat}",
        "destination": f"{dest_lng},{dest_lat}",
    }
    resp = requests.get(url, headers=headers, params=params, timeout=5)
    resp.raise_for_status()
    data = resp.json()
    route = data["routes"][0]
    summary = route["summary"]

    path: list[tuple[float, float]] = []
    for section in route.get("sections", []):
        for road in section.get("roads", []):
            vertexes = road.get("vertexes", [])
            for i in range(0, len(vertexes) - 1, 2):
                lng, lat = vertexes[i], vertexes[i + 1]
                path.append((lat, lng))
    if not path:
        # 폴백: 도로 구간 정보가 없으면 최소한 시작/끝 직선이라도 제공
        path = [(origin_lat, origin_lng), (dest_lat, dest_lng)]

    return {
        "distance_km": summary["distance"] / 1000,
        "duration_min": summary["duration"] / 60,
        "path": path,
    }


def estimate_truck_fare(distance_km: float, weight_ton: float) -> int:
    """거리+중량 기반 근사 요금 (원). ⚠️ 추정치."""
    fare = (
        TRUCK_FARE_BASE_WON
        + distance_km * TRUCK_FARE_PER_KM_WON
        + weight_ton * TRUCK_FARE_PER_TON_WON
    )
    return round(fare, -3)  # 천원 단위 반올림


def estimate_quick_fare(distance_km: float, weight_kg: float) -> int | None:
    """근거리 급행 근사 요금 (원). 중량 초과 시 None(이용 불가)."""
    if weight_kg > QUICK_MAX_WEIGHT_KG:
        return None
    fare = QUICK_FARE_BASE_WON + distance_km * QUICK_FARE_PER_KM_WON
    return round(fare, -3)


def estimate_drayage_fare(distance_km: float, weight_ton: float) -> int:
    """첫마일/막판마일 근거리 운송 근사 요금 (원). ⚠️ 추정치."""
    fare = (
        DRAYAGE_BASE_WON
        + distance_km * TRUCK_FARE_PER_KM_WON
        + weight_ton * TRUCK_FARE_PER_TON_WON
    )
    return round(fare, -3)
