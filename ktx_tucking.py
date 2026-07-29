# -*- coding: utf-8 -*-
"""
KTX특송(짐캐리 운영) 규격·요금 근사 데이터.

⚠️ 아래 요금 수치는 예시 플레이스홀더입니다.
   제출 전 https://zimcarry.net 공식 요금표를 확인해 실제 값으로
   교체해야 합니다. (본 코드는 임의로 가격을 지어내지 않기 위해
   구조만 정확히 맞추고 숫자는 TODO로 표시합니다.)

핵심 제약:
   - 같은 노선(같은 선로)의 두 역 간에만 가능 (예: 경부선-호남선 간 불가)
   - 취급역이 제한적 (전국 15개 역 내외, 시기별로 변동 있음 — 최신 확인 필요)
   - 규격 초과 시 KTX특송 이용 불가 → 철도 통합운송 또는 트럭/퀵으로 분기
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class KtxTuckingTier:
    label: str
    max_long_side_cm: float
    max_sum_3sides_cm: float
    max_weight_kg: float
    base_fare_won: int  # TODO: 실제 공시요금으로 교체


KTX_TUCKING_TIERS: list[KtxTuckingTier] = [
    # 초소형 (일부 KTX 특정 열차 전용)
    KtxTuckingTier("초소형", 25, 999, 2, 15000),   # TODO: 요금 확인
    # 소형 (SRT 등)
    KtxTuckingTier("소형", 60, 120, 15, 25000),    # TODO: 요금 확인
]

# 취급역 목록 — ⚠️ 시기별로 변동 (2025년 포항/익산 종료, 여수엑스포 공사중단 등)
# 제출 전 짐캐리 홈페이지에서 최신 목록 재확인 필요
KTX_TUCKING_STATIONS = [
    "서울역", "광명역", "동탄역", "천안아산역", "오송역",
    "대전역", "동대구역", "경주역", "부산역",
]

# 노선 그룹 (같은 그룹 내에서만 특송 가능, 근사)
LINE_GROUPS = {
    "경부선": ["서울역", "광명역", "천안아산역", "오송역", "대전역", "동대구역", "경주역", "부산역"],
    "호남선": ["서울역", "광명역", "천안아산역", "오송역"],  # 이후 호남 방면
    "SRT_동탄": ["동탄역"],
}


def check_ktx_tucking_eligible(
    origin_station: str,
    dest_station: str,
    long_side_cm: float,
    sum_3sides_cm: float,
    weight_kg: float,
) -> tuple[bool, str]:
    """규격·역·노선 조건을 모두 확인해 KTX특송 이용 가능 여부 판정."""
    if origin_station not in KTX_TUCKING_STATIONS or dest_station not in KTX_TUCKING_STATIONS:
        return False, "취급역이 아닙니다."

    same_line = any(
        origin_station in stations and dest_station in stations
        for stations in LINE_GROUPS.values()
    )
    if not same_line:
        return False, "같은 노선(선로) 내에서만 특송이 가능합니다."

    for tier in KTX_TUCKING_TIERS:
        if (
            long_side_cm <= tier.max_long_side_cm
            and sum_3sides_cm <= tier.max_sum_3sides_cm
            and weight_kg <= tier.max_weight_kg
        ):
            return True, f"{tier.label} 규격으로 이용 가능"

    return False, "규격(크기/무게) 초과로 이용 불가"
