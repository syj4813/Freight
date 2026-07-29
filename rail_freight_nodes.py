# -*- coding: utf-8 -*-
"""
철도 화물 결절점(화물역) 좌표 및 근사 상수.

⚠️ TAGO API는 여객열차 정보만 제공하며, 화물열차 실시간 시각표는
   공개 API가 없습니다(코레일 내부 LOGIS 시스템에서만 관리).
   따라서 이 파일의 소요시간/운임은 "근사치"이며, 화면에는 반드시
   '추정치' 라벨과 함께 표시해야 합니다.

전철화 여부(electrified)는 나무위키 "철도 노선 정보/대한민국" 문서의
노선별 전철화 표를 참고했습니다. 위키 문서라 신뢰도는 국가철도공단
공식 자료보다 낮으므로, 제출 전 교차 검증을 권장합니다.
  - 남부화물기지선(의왕~오봉): 전철화 O
  - 부산신항선(진례~부산신항): 전철화 O
  - 경부선 본선(부산진역, 대구역, 오송역 접속): 전철화 O
  - 광양항선: 비전철 (X)
  - 여천선 계열(여수국가산단역 인근): 비전철 (X)

TODO(제출 전 확인 필요):
   - RAIL_TON_KM_RATE: 실제 화물역 간 계약운임 사례나 국토부 자료로 보정
   - AVG_FREIGHT_SPEED_KMH: 화물열차 평균 표정속도 공식 자료로 보정
   - electrified 값: 국가철도공단/코레일 공식 자료로 교차 검증
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FreightNode:
    name: str
    lat: float
    lng: float
    region: str
    electrified: bool  # 접속 지선 기준 전철화 여부 (나무위키 참고, 교차검증 필요)


# 주요 화물역/화물기지 좌표 (근사치, 실제 역 대표 좌표 기준)
FREIGHT_NODES: list[FreightNode] = [
    FreightNode("의왕ICD", 37.3308, 126.9683, "수도권", electrified=True),
    FreightNode("오봉역", 37.4256, 126.9008, "수도권", electrified=True),
    FreightNode("부산신항역", 35.0762, 128.8095, "부산·경남", electrified=True),
    FreightNode("부산진역", 35.1298, 129.0403, "부산·경남", electrified=True),
    FreightNode("대구역(화물)", 35.8763, 128.5940, "대구·경북", electrified=True),
    FreightNode("오송역(화물)", 36.6200, 127.3290, "충청", electrified=True),
    FreightNode("여수국가산단역", 34.7604, 127.6622, "전남", electrified=False),
    FreightNode("광양항역", 34.9070, 127.7570, "전남", electrified=False),
]

# 화물역 간 컨테이너(20피트, 최대 약 20톤) 적재 기준 — 단독 발송 판정용
CONTAINER_MAX_TON = 20.0

# LCL(소량 컨테이너 화물) 개념의 최소 결합 기준 — 여러 화주를 합쳐
# 철도가 경제적으로 유리해지는 최소 물량. 컨테이너를 완전히 채울 필요는
# 없고, 포워더가 여러 화주 화물을 나눠 싣는 공유 적재가 실무에서 일반적.
# ⚠️ 추정치 — 실제로는 화물 부피(CBM), 화물 종류(혼적 가능 여부),
# 코레일/포워더와의 최소 물량 계약 조건 등으로 결정되므로 국토부/
# 물류업계 자료로 보정 필요.
MIN_CONSOLIDATION_TON = 5.0

# 화물열차 평균 표정속도 근사치 (km/h) — ⚠️ 추정치, 공식 자료로 보정 필요
AVG_FREIGHT_SPEED_KMH = 45.0

# 톤·km 당 근사 운임 (원) — ⚠️ 추정치. 코레일 화물 운임은 계약 기반 비공개.
# 국토부 물류 통계상 도로 대비 철도가 대략 1/3~1/2 수준이라는 공개 자료를
# 참고해 트럭 요금 대비 상대적으로 낮게 설정한 잠정값입니다.
RAIL_TON_KM_RATE_WON = 55  # 원/톤·km, TODO: 실제 자료로 보정

# 화물역 입출고(상하차, 마지막 트럭 연계) 고정 소요시간 (분)
TERMINAL_HANDLING_MIN = 60
