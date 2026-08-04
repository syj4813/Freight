# -*- coding: utf-8 -*-
"""공용 상수 모듈.

⚠️ 병합 전 이 파일에는 화주/화물/트럭기사 데이터를 random으로 생성하는
함수들(generate_shipments, generate_return_cargo_options, generate_driver_today,
generate_network_snapshot, kpi_before_after)이 있었다. 병합하면서 전부 제거했고,
해당 데이터는 이제 shared_store.read_shipments()의 실측 예약 데이터에서 계산한다.

STATIONS는 Freight의 rail_freight_nodes.FREIGHT_NODES와 동일 7개 역이며,
값을 여기서 다시 정의하지 않고 직접 import해서 쓴다 — 두 군데서 좌표를
따로 관리하면 다시 어긋나기 때문 (병합 전 발견됐던 문제).
"""

from rail_freight_nodes import FREIGHT_NODES

STATIONS = {node.name: (node.lat, node.lng) for node in FREIGHT_NODES}

CARGO_TYPES = ["컨테이너 20FT", "컨테이너 40FT", "냉동 컨테이너", "일반 화물"]

# 기사별 현재 위치 — 실제 GPS 연동 전이라 하드코딩. 7개 화물역에 1명씩
# 배치해 트럭기사 앱에서 화물역별 매칭 후보를 데모로 확인할 수 있게 함.
DRIVER_CURRENT_STATION = {
    "김도현": "오봉역",
    "이수민": "의왕역",
    "박정우": "부산항역(신항)",
    "최은서": "부산진역",
    "장민호": "천안역",
    "한지수": "순천역",
    "오세훈": "포항역",
}

DRIVER_NAMES = list(DRIVER_CURRENT_STATION.keys())
