# -*- coding: utf-8 -*-
"""철도(화물역 간) 구간 근사 요금/시간 계산."""

import math

from rail_freight_nodes import (
    FREIGHT_NODES,
    AVG_FREIGHT_SPEED_KMH,
    RAIL_TON_KM_RATE_WON,
    TERMINAL_HANDLING_MIN,
    FreightNode,
)


def _haversine_km(lat1, lng1, lat2, lng2) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def nearest_freight_node(lat: float, lng: float) -> tuple[FreightNode, float]:
    """화주 위치에서 가장 가까운 화물역과 거리(km) 반환."""
    best, best_dist = None, float("inf")
    for node in FREIGHT_NODES:
        d = _haversine_km(lat, lng, node.lat, node.lng)
        if d < best_dist:
            best, best_dist = node, d
    return best, best_dist


def estimate_rail_leg(origin_node: FreightNode, dest_node: FreightNode) -> dict:
    """화물역 간 구간 근사 소요시간(분)/운임(원, 톤당) + 전철화 여부 판정.

    ⚠️ 소요시간·운임은 추정치. 전철화 여부는 각 화물역 접속 지선의
    실제 전철화 상태(나무위키 참고, 교차검증 필요)를 근거로 판정 —
    두 노드가 모두 전철화된 경우만 '전철', 하나라도 비전철이면 '디젤'로
    간주 (디젤기관차가 전 구간을 견인하는 실무 관행을 단순화한 가정).
    """
    if origin_node.name == dest_node.name:
        return {"distance_km": 0, "duration_min": 0, "won_per_ton": 0, "electrified": True}

    dist_km = _haversine_km(
        origin_node.lat, origin_node.lng, dest_node.lat, dest_node.lng
    )
    duration_min = (dist_km / AVG_FREIGHT_SPEED_KMH) * 60 + TERMINAL_HANDLING_MIN * 2
    won_per_ton = dist_km * RAIL_TON_KM_RATE_WON
    electrified = origin_node.electrified and dest_node.electrified
    return {
        "distance_km": round(dist_km, 1),
        "duration_min": round(duration_min),
        "won_per_ton": round(won_per_ton),
        "electrified": electrified,
    }
