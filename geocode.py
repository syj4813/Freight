# -*- coding: utf-8 -*-
"""Google Geocoding API 래퍼 — 주소 -> (lat, lng)."""

import requests

GOOGLE_MAPS_API_KEY = ""  # TODO: Streamlit secrets 등으로 주입


def geocode_address(address: str) -> tuple[float, float] | None:
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": address, "key": GOOGLE_MAPS_API_KEY, "language": "ko"}
    resp = requests.get(url, params=params, timeout=5)
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") != "OK" or not data.get("results"):
        return None
    loc = data["results"][0]["geometry"]["location"]
    return loc["lat"], loc["lng"]
