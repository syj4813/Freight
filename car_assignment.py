# -*- coding: utf-8 -*-
"""화차 배치 추천 — 서모게이트 LightGBM 모델(150개 트리) 파이썬 이식.

⚠️ 이 모델은 사용자가 별도로 학습해 브라우저 데모(HTML)로 만든 걸 그대로
   가져온 것입니다. 트리 구조(car_assignment_model.json)는 실제 학습된
   가중치이고, 여기서는 그 트리를 순회해 추론(evalTree/predict)하는
   로직만 JS에서 Python으로 옮겼습니다 — 새 모델을 만들거나 재학습한
   게 아닙니다.
⚠️ 다만 학습에 쓰인 정답 라벨(suitability_score)은 실제 코레일 배치
   결과가 아니라 사용자가 자체 정의한 합성 규칙 기반 라벨입니다. 즉
   "모델링 방식은 진짜, 배우는 대상(정답)은 자체 정의"라는 한계가 있고,
   실제 운영 기준 정확도를 보장하지 않습니다 (원본 데모의 고지 그대로).
⚠️ 화차 편성(개별 화차 타입/최대적재량/현재적재량/위험물차 위치) 데이터는
   코레일에서 아직 못 받아서, 이 모듈이 자체적으로 mock 편성을 생성합니다
   (generate_mock_train_composition). random이 아니라 열차번호를 시드로 한
   결정론적 생성이라 같은 열차는 항상 같은 편성이 나옵니다 — 그래도
   "실제 편성"은 아니라는 점은 동일합니다.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

MODEL_PATH = Path(__file__).parent / "car_assignment_model.json"

CAR_TYPES = ["무개차", "유개차", "컨테이너차", "탱크차", "평판차"]
POSITIONS = ["전부", "중부", "후부"]

_model_cache: dict | None = None


def _get_model() -> dict:
    global _model_cache
    if _model_cache is None:
        with open(MODEL_PATH, encoding="utf-8") as f:
            _model_cache = json.load(f)
    return _model_cache


def _eval_tree(node: dict, x: list) -> float:
    if "leaf" in node:
        return node["leaf"]
    v = x[node["f"]]
    go_left = node["dl"] if v is None else (v <= node["th"])
    return _eval_tree(node["l"] if go_left else node["r"], x)


def predict_raw(x: list) -> float:
    """트리 150개 리프값 합산 — JS predict()와 동일 로직."""
    model = _get_model()
    return sum(_eval_tree(t, x) for t in model["trees"])


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


@dataclass
class TrainCar:
    car_index: int  # 1-base
    car_type: str
    max_load_kg: float
    current_load_kg: float
    remaining_capacity_m3: float
    distance_from_hazmat_car: int  # 위험물차와 몇 칸 떨어져 있는지
    position: str  # 전부/중부/후부 (car_index/total_cars 비율로 결정)


def _derive_position(car_index: int, total_cars: int) -> str:
    rel = car_index / total_cars
    if rel <= 1 / 3:
        return "전부"
    if rel <= 2 / 3:
        return "중부"
    return "후부"


def generate_mock_train_composition(train_no: str, total_cars: int = 20) -> list[TrainCar]:
    """열차번호를 시드로 한 결정론적 mock 화차 편성 생성.

    ⚠️ 실제 편성 데이터가 없어 만든 대체값입니다. 화차 종류는 열차번호
    해시로 순환 배정하고, 적재량은 화차 종류별 그럴듯한 범위 안에서
    해시 기반으로 정합니다 — random.random()이 아니라 hashlib 기반이라
    같은 열차번호는 항상 같은 편성이 나옵니다(재현 가능).
    """
    seed = int(hashlib.sha256(train_no.encode()).hexdigest(), 16)
    cars = []
    hazmat_car_index = 1 + (seed % total_cars)  # 위험물(탱크차) 위치 하나 고정 배정
    for i in range(1, total_cars + 1):
        local_seed = (seed + i * 7919) % (2**32)
        if i == hazmat_car_index:
            car_type = "탱크차"
        else:
            car_type = CAR_TYPES[(local_seed // 97) % len(CAR_TYPES)]
        max_load = {"무개차": 40000, "유개차": 35000, "컨테이너차": 45000,
                    "탱크차": 38000, "평판차": 42000}[car_type]
        current_load = max_load * (0.1 + (local_seed % 60) / 100)  # 10~70% 적재 중
        remaining_vol = 5.0 + (local_seed % 400) / 10  # 5.0~44.9 m3
        cars.append(TrainCar(
            car_index=i,
            car_type=car_type,
            max_load_kg=round(max_load),
            current_load_kg=round(current_load),
            remaining_capacity_m3=round(remaining_vol, 1),
            distance_from_hazmat_car=abs(i - hazmat_car_index),
            position=_derive_position(i, total_cars),
        ))
    return cars


def recommend_cars(
    cargo_weight_kg: float,
    cargo_length_cm: float,
    cargo_width_cm: float,
    cargo_height_cm: float,
    hazmat: bool,
    fragile: bool,
    cars: list[TrainCar],
    top_n: int = 5,
) -> list[dict]:
    """화차 편성 전체에 대해 적합도 점수를 계산해 상위 top_n 반환."""
    model = _get_model()
    feature_names: list[str] = model["feature_names"]
    encoders: dict = model["encoders"]
    total_cars = len(cars)

    results = []
    for car in cars:
        feat = {
            "cargo_weight_kg": cargo_weight_kg,
            "cargo_length_cm": cargo_length_cm,
            "cargo_width_cm": cargo_width_cm,
            "cargo_height_cm": cargo_height_cm,
            "hazmat_class": 1 if hazmat else 0,
            "fragile_flag": 1 if fragile else 0,
            "train_total_cars": total_cars,
            "car_index": car.car_index,
            "car_type_enc": encoders["car_type"].index(car.car_type),
            "car_max_load_kg": car.max_load_kg,
            "car_current_load_kg": car.current_load_kg,
            "car_remaining_capacity_m3": car.remaining_capacity_m3,
            "distance_from_hazmat_car": car.distance_from_hazmat_car,
            "position_in_car_enc": encoders["position_in_car"].index(car.position),
        }
        x = [feat[name] for name in feature_names]
        score = _clamp01(predict_raw(x))
        remaining_capacity_kg = car.max_load_kg - car.current_load_kg
        results.append({
            "car": car,
            "score": round(score, 4),
            "capacity_ok": remaining_capacity_kg >= cargo_weight_kg,
        })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:top_n]
