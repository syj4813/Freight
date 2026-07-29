# -*- coding: utf-8 -*-
"""
철도 통합운송 door-to-door 계산.

⚠️ 이전 버전은 '철도 통합운송' 수단을 화물역 간 구간만으로 계산했음 —
   실제로는 화주 문 앞에서 출발 화물역까지, 도착 화물역에서 최종
   도착지까지 트럭으로 옮기는 첫마일/막판마일이 반드시 필요함.
   이를 빼놓으면 시간·요금·배출량이 전부 과소평가됨. 이 모듈은
   첫마일(트럭) + 철도 구간 + 막판마일(트럭)을 합산한다.
"""

from dataclasses import dataclass

from rail_cost import nearest_freight_node, estimate_rail_leg
from road_cost import get_road_distance_duration, estimate_drayage_fare
from emission import calculate_emission, TransportMode


@dataclass
class IntermodalResult:
    total_duration_min: int
    total_fare_won: int
    total_gwp_kg_co2e: float
    total_pm_kg: float
    electrified: bool
    origin_node_name: str
    dest_node_name: str
    first_mile_km: float
    rail_km: float
    last_mile_km: float


def estimate_intermodal(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    weight_ton: float,
) -> IntermodalResult:
    origin_node, _ = nearest_freight_node(origin_lat, origin_lng)
    dest_node, _ = nearest_freight_node(dest_lat, dest_lng)

    # 첫마일: 화주 출발지 -> 가장 가까운 출발 화물역 (카카오맵 실제 도로 데이터)
    first_mile = get_road_distance_duration(origin_lng, origin_lat, origin_node.lng, origin_node.lat)
    # 막판마일: 도착 화물역 -> 화주 최종 도착지
    last_mile = get_road_distance_duration(dest_node.lng, dest_node.lat, dest_lng, dest_lat)

    rail_leg = estimate_rail_leg(origin_node, dest_node, weight_ton)

    first_mile_fare = estimate_drayage_fare(first_mile["distance_km"], weight_ton)
    last_mile_fare = estimate_drayage_fare(last_mile["distance_km"], weight_ton)

    total_duration = first_mile["duration_min"] + rail_leg["duration_min"] + last_mile["duration_min"]
    total_fare = first_mile_fare + rail_leg["fare_won"] + last_mile_fare

    rail_mode = TransportMode.RAIL_FREIGHT_ELECTRIC if rail_leg["electrified"] else TransportMode.RAIL_FREIGHT_DIESEL
    rail_emission = calculate_emission(rail_mode, rail_leg["distance_km"], weight_ton)
    first_mile_emission = calculate_emission(TransportMode.TRUCK_LORRY_3_5_7_5T, first_mile["distance_km"], weight_ton)
    last_mile_emission = calculate_emission(TransportMode.TRUCK_LORRY_3_5_7_5T, last_mile["distance_km"], weight_ton)

    total_gwp = (
        rail_emission["gwp_kg_co2e"]
        + first_mile_emission["gwp_kg_co2e"]
        + last_mile_emission["gwp_kg_co2e"]
    )
    total_pm = (
        rail_emission["pm_kg"] + first_mile_emission["pm_kg"] + last_mile_emission["pm_kg"]
    )

    return IntermodalResult(
        total_duration_min=round(total_duration),
        total_fare_won=round(total_fare, -3),
        total_gwp_kg_co2e=round(total_gwp, 3),
        total_pm_kg=round(total_pm, 6),
        electrified=rail_leg["electrified"],
        origin_node_name=origin_node.name,
        dest_node_name=dest_node.name,
        first_mile_km=first_mile["distance_km"],
        rail_km=rail_leg["distance_km"],
        last_mile_km=last_mile["distance_km"],
    )
