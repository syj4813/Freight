# -*- coding: utf-8 -*-
"""
이동경로 지도 시각화 (pydeck).

트럭 직송 구간(주황색)과, 철도 통합운송이 가능한 경우 첫마일/철도/막판마일
구간(초록/파랑/초록)을 지도 위에 선으로 표시한다. Mapbox 토큰 없이도
pydeck 기본 제공 베이스맵(Carto)으로 렌더링된다.
"""

import pydeck as pdk

TRUCK_COLOR = [255, 140, 0]
DRAYAGE_COLOR = [34, 139, 34]
RAIL_COLOR = [30, 90, 220]
ORIGIN_COLOR = [0, 102, 255]
DEST_COLOR = [220, 20, 60]
NODE_COLOR = [34, 139, 34]


def build_route_map(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    origin_node: tuple[float, float, str] | None = None,
    dest_node: tuple[float, float, str] | None = None,
) -> pdk.Deck:
    """origin_node/dest_node를 (lat, lng, 역이름) 튜플로 주면 철도 경로도 함께 표시."""
    markers = [
        {"lat": origin_lat, "lng": origin_lng, "label": "출발지", "color": ORIGIN_COLOR},
        {"lat": dest_lat, "lng": dest_lng, "label": "도착지", "color": DEST_COLOR},
    ]
    paths = [
        {"path": [[origin_lng, origin_lat], [dest_lng, dest_lat]], "color": TRUCK_COLOR, "label": "트럭 직송"},
    ]

    if origin_node and dest_node:
        on_lat, on_lng, on_name = origin_node
        dn_lat, dn_lng, dn_name = dest_node
        markers.append({"lat": on_lat, "lng": on_lng, "label": on_name, "color": NODE_COLOR})
        markers.append({"lat": dn_lat, "lng": dn_lng, "label": dn_name, "color": NODE_COLOR})
        paths.append({"path": [[origin_lng, origin_lat], [on_lng, on_lat]], "color": DRAYAGE_COLOR, "label": "첫마일(트럭)"})
        paths.append({"path": [[on_lng, on_lat], [dn_lng, dn_lat]], "color": RAIL_COLOR, "label": "철도"})
        paths.append({"path": [[dn_lng, dn_lat], [dest_lng, dest_lat]], "color": DRAYAGE_COLOR, "label": "막판마일(트럭)"})

    path_layer = pdk.Layer(
        "PathLayer",
        data=paths,
        get_path="path",
        get_color="color",
        get_width=5,
        width_min_pixels=3,
        pickable=True,
    )
    marker_layer = pdk.Layer(
        "ScatterplotLayer",
        data=markers,
        get_position=["lng", "lat"],
        get_fill_color="color",
        get_radius=6000,
        pickable=True,
    )
    text_layer = pdk.Layer(
        "TextLayer",
        data=markers,
        get_position=["lng", "lat"],
        get_text="label",
        get_size=14,
        get_color=[20, 20, 20],
        get_pixel_offset=[0, -14],
    )

    view_state = pdk.ViewState(
        latitude=(origin_lat + dest_lat) / 2,
        longitude=(origin_lng + dest_lng) / 2,
        zoom=6.2,
    )

    return pdk.Deck(
        layers=[path_layer, marker_layer, text_layer],
        initial_view_state=view_state,
        tooltip={"text": "{label}"},
    )
