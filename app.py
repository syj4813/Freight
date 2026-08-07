# -*- coding: utf-8 -*-
"""진입점 — st.navigation()으로 각 화면을 라우팅.

⚠️ 2026-08-08 수정: 기존에는 app.py 자체가 화주용 견적비교 화면이었고,
   pages/ 폴더의 한글 파일명을 코드에서 문자열로 직접 참조했습니다. 이
   방식이 플랫폼(macOS git 유니코드 정규화, Windows GitHub 웹 업로드
   등)에 따라 파일명이 미묘하게 달라지는 문제를 반복적으로 일으켜서,
   파일명은 전부 영문(ASCII)으로 바꾸고 화면에 보이는 한글 이름은
   st.Page(title=...)로 따로 지정하는 방식으로 바꿨습니다. 실제 화주용
   견적비교 화면 내용은 pages/page0_home.py로 옮겼습니다 — 로직 자체는
   그대로이고 파일 위치만 바뀐 것입니다.
"""

import streamlit as st

pg = st.navigation([
    st.Page("pages/page0_home.py", title="소량 화물 운송수단 비교", icon="🏠", default=True),
    st.Page("pages/page1_shipper_tracking.py", title="화주용 실시간추적", icon="📦"),
    st.Page("pages/page2_driver_app.py", title="트럭기사용 앱", icon="🚚"),
    st.Page("pages/page3_control_tower.py", title="관제센터", icon="🛰️"),
    st.Page("pages/page4_car_assignment.py", title="화차 배치 추천", icon="🚃"),
])
pg.run()
