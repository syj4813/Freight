# -*- coding: utf-8 -*-
"""
한국 표준시(KST, UTC+9) 기준 날짜/시각 헬퍼.

⚠️ Streamlit Cloud 등 배포 서버는 기본적으로 UTC로 동작합니다.
   date.today()/datetime.now()를 그냥 쓰면 서버 시간대에 따라
   날짜가 최대 하루 어긋날 수 있습니다 (특히 한국 자정 전후,
   UTC 기준 오후 3시~다음날 오전 사이). 화물열차 요일 매칭처럼
   날짜에 민감한 로직이 있어 반드시 KST로 고정해야 합니다.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def now_kst() -> datetime:
    """타임존 정보가 붙은 현재 KST 시각."""
    return datetime.now(KST)


def today_kst():
    """현재 KST 기준 날짜(date)."""
    return now_kst().date()
