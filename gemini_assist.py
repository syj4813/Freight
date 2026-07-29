# -*- coding: utf-8 -*-
"""
Gemini(Agent Platform express mode) 활용 — 역할을 의도적으로 제한한다.

  - 하지 않는 것: 경로 최적화, 통합 판정, 요금 계산 (전부 결정론적
    로직으로 처리 — 재현성과 설명가능성 확보 목적)
  - 하는 것: (1) 화주의 자연어 입력을 구조화된 필드로 파싱
             (2) 계산된 비교 결과를 화주에게 설명하는 문장 생성
             (3) 화물 종류를 카테고리로 분류

인증 방식: "Agent Platform Model APIs" 키(AQ.로 시작하는 형식)를
공식 google-genai SDK의 express mode(`vertexai=True, api_key=...`)로
사용. 서비스 계정 JSON이나 프로젝트 ID 없이 API 키 하나로 인증되며,
Google Cloud 무료 크레딧을 그대로 소진할 수 있음.
"""

import json

from google import genai

GEMINI_API_KEY = ""  # TODO: Streamlit secrets 등으로 주입 (Agent Platform Model APIs 키)
GEMINI_MODEL = "gemini-3.5-flash"


def _call_gemini(prompt: str) -> str:
    client = genai.Client(vertexai=True, api_key=GEMINI_API_KEY)
    response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    return response.text


def parse_free_text_order(text: str) -> dict:
    """자연어 입력 -> 구조화된 필드(JSON) 파싱."""
    prompt = f"""다음 화물 운송 요청 문장에서 정보를 추출해 JSON으로만 답하세요.
필드: origin(출발지), destination(도착지), cargo_type(화물종류),
weight_kg(중량, 숫자만), desired_date(YYYY-MM-DD, 알 수 없으면 null)

문장: "{text}"

JSON만 출력하세요. 다른 설명은 붙이지 마세요."""
    raw = _call_gemini(prompt)
    cleaned = raw.strip().removeprefix("```json").removesuffix("```").strip()
    return json.loads(cleaned)


CARGO_CATEGORIES = ["일반화물", "냉장·냉동", "위험물", "파손주의·고가품", "농산물·생물"]


def classify_cargo_category(cargo_type_text: str) -> str:
    """화물 종류 자연어 입력을 5개 카테고리 중 하나로 분류.

    키워드 매칭(cargo.classify_cargo_type)과 달리 목록에 없는 표현
    (예: "방사성물질")도 의미 기반으로 처리 가능. 단, LLM 특성상
    실행마다 결과가 미세하게 달라질 수 있어 재현성은 키워드 방식보다
    낮음 — 이 트레이드오프를 알고 쓰는 것.
    """
    prompt = f"""다음 화물 종류를 아래 카테고리 중 정확히 하나로 분류하세요.
카테고리: {", ".join(CARGO_CATEGORIES)}

화물 종류: "{cargo_type_text}"

카테고리 이름 하나만 정확히 출력하세요. 다른 설명은 붙이지 마세요."""
    raw = _call_gemini(prompt).strip()
    for category in CARGO_CATEGORIES:
        if category in raw:
            return category
    return "일반화물"  # 매칭 실패 시 보수적으로 일반화물 처리


def explain_comparison(comparison_rows: list[dict], consolidation_note: str) -> str:
    """계산된 비교 결과를 화주 친화적 문장으로 요약."""
    prompt = f"""아래는 화물 운송 수단별 비교 계산 결과입니다. 화주에게 보여줄
2~3문장의 친절한 요약을 존댓말로 작성하세요. 숫자를 새로 만들어내지 말고
주어진 데이터만 근거로 설명하세요.

비교 데이터: {json.dumps(comparison_rows, ensure_ascii=False)}
철도 통합운송 판정 메모: {consolidation_note}"""
    return _call_gemini(prompt)
