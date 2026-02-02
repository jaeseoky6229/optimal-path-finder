"""
반영 내용:
- 출장 가능 일자 근무 시작/끝을 day_windows_json으로 입력받아 적용
- Day별 허용시간 = (끝-시작) 분
- 최대 30일까지만 배정, 입력한 출장 가능 일수로 진행, 초과는 unscheduled
- 일괄적용 체크 시 점검시간 전체 덮어쓰기
- Day별 start_time 반영한 end_time 계산

- ✅ 최적화 알고리즘(복합 휴리스틱):
  - 전역 순서 후보: (NN + 랜덤 NN 멀티스타트) -> (선택)2-opt
  - day split: DP로 연속 구간 분할
  - 후보 평가 목적함수(작을수록 좋음):
    1) scheduled_count 최대화  -> -scheduled_count 최소화
    2) used_days 최소화
    3) last_day_total 최소화   (✅ depot 최종 복귀 포함)
    4) total_move 최소화       (✅ depot 최종 복귀 이동 포함)

- ✅ 정책(중요):
  - 매일 depot 복귀 X, 다음날은 전날 마지막 위치에서 출발
  - ✅ 최종 depot 복귀는 필수 + 하드 제약
    - 마지막 day에 복귀까지 못 넣으면, 다음날 "복귀만 하는 day"로 미룸(가능하면)

- ✅ 재현성/일관성:
  - 시간(이동시간/도착시각/제약검사/total)은 100% time_mat 기준
  - kakao_route_edge()는 폴리라인(path)만 획득(표시용), duration은 사용하지 않음

- ✅ NEW (자동 선택):
  - 선택 교량의 관할청(office)이 2개 이상이면 GA 사용 (dp_split 미사용)
  - 단일 관할청이면 기존 휴리스틱+DP 사용

- ✅ NEW (필수/마감):
  - 클라이언트에서 mandatory_rules(bridge_id별 required/deadline_day)를 받아
    DP split 단계에서 필수/마감 Day를 하드 제약으로 강제 (dp_split.py 수정본 연결)
  - 결과 schedule에 mandatory_meta를 포함해 프론트에서 경고 표시 가능
"""

import math
import os, json
import sys
from typing import Dict, Tuple, List, Any, Optional

import pandas as pd
from flask import Flask, request, jsonify, render_template

# === 서비스 모듈 import ===
from services.cache_utils import load_json_cache, save_json_cache, route_cache_key
from services.excel_service import normalize_columns, load_bridge_database
from services.kakao_client import kakao_geocode, kakao_route_edge
from services.config_loader import load_config


# === 최적화 모듈 import (✅ 새 구조 반영) ===
from optimize.route_heuristics import (
    make_candidate_routes_multistart,
    two_opt_chain_from_start,
    nearest_neighbor_route_from_start,
)

from optimize.route_ga import (
    solve_ga_multiday_no_return,
)

from optimize.dp_split import (
    dp_split_days_with_final_return_varlimits,
    dp_split_days_no_return_varlimits,
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def resource_path(*parts: str) -> str:
    """
    - py 실행: main_program.py 기준
    - pyinstaller onefile: sys._MEIPASS 기준(압축 풀린 임시 폴더)
    - pyinstaller onedir: exe가 있는 폴더 기준
    """
    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            base = sys._MEIPASS
        else:
            base = os.path.dirname(sys.executable)
    else:
        base = BASE_DIR
    return os.path.join(base, *parts)

app = Flask(
    __name__,
    template_folder=resource_path("templates"),
    static_folder=resource_path("static"),
)

CONFIG = load_config()

if not CONFIG["KAKAO_REST_API_KEY"]:
    raise RuntimeError(
        "KAKAO_REST_API_KEY가 없습니다.\n"
        "- exe와 같은 폴더에 config.json을 생성하고\n"
        '- {"KAKAO_REST_API_KEY":"...", "KAKAO_JS_API_KEY":"..."} 형태로 입력하세요.\n'
        f"(찾는 경로: {CONFIG.get('_CONFIG_PATH')}, 존재여부: {CONFIG.get('_CONFIG_FOUND')})"
    )

# =======================
# 설정
# =======================

DEFAULT_INSPECT_MIN = 60

DAY_START_HOUR = 8
DAY_START_MINUTE = 0

DAY_LIMIT_TOTAL_MIN_DEFAULT = 8 * 60   # 480
DAY_LIMIT_MOVE_MIN_DEFAULT = 4 * 60    # 240

KAKAO_REST_API_KEY = CONFIG["KAKAO_REST_API_KEY"]

DATA_DIR = resource_path("data")

BRIDGE_DB_PATH = os.path.join(DATA_DIR, "bridge_database.xlsx")
GEOCODE_CACHE_PATH = os.path.join(DATA_DIR, "geocode_cache.json")
REGISTRY_PATH = os.path.join(DATA_DIR, "bridge_id_registry.json")
ROUTE_CACHE_PATH = os.path.join(DATA_DIR, "route_cache.json")

EXCEL_SHEET_NAME = "Sheet1"

COORD_ROUND_DIGITS = 6

ROUTING_MODE_APPROX = "approx"
ROUTING_MODE_REAL_MATRIX = "real_matrix"

MAX_DAYS = 7


print("CWD:", os.getcwd())
print("__file__:", __file__)
print("BRIDGE_DB_PATH:", BRIDGE_DB_PATH)
print("Exists bridge db:", os.path.exists(BRIDGE_DB_PATH))
print("Exists data dir:", os.path.exists(DATA_DIR))

def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)

def normalize_route_cache_path(raw: Optional[str]) -> str:
    p = (raw or "").strip()
    if not p:
        p = ROUTE_CACHE_PATH

    if not p.lower().endswith(".json"):
        p = p + ".json"

    if not os.path.isabs(p):
        if not (p.startswith(DATA_DIR + os.sep) or p.startswith(DATA_DIR + "/")):
            p = os.path.join(DATA_DIR, p)

    return p

def load_geocode_cache() -> dict:
    _ensure_data_dir()
    if not os.path.exists(GEOCODE_CACHE_PATH):
        return {}
    try:
        with open(GEOCODE_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}

def save_geocode_cache(cache: dict):
    _ensure_data_dir()
    with open(GEOCODE_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def hydrate_latlng_from_cache(df: pd.DataFrame, cache: dict) -> pd.DataFrame:
    def _get_lat(addr):
        v = cache.get(addr)
        return (v or {}).get("lat") if isinstance(v, dict) else None

    def _get_lng(addr):
        v = cache.get(addr)
        return (v or {}).get("lng") if isinstance(v, dict) else None

    if "address" not in df.columns:
        return df

    if "lat" not in df.columns:
        df["lat"] = None
    if "lng" not in df.columns:
        df["lng"] = None

    miss_lat = df["lat"].isna()
    miss_lng = df["lng"].isna()
    miss = miss_lat | miss_lng

    if miss.any():
        df.loc[miss_lat, "lat"] = df.loc[miss_lat, "address"].map(_get_lat)
        df.loc[miss_lng, "lng"] = df.loc[miss_lng, "address"].map(_get_lng)

    return df


# =======================
# 시간/파싱 유틸
# =======================
def parse_hhmm_to_min(hhmm: str) -> Optional[int]:
    s = str(hhmm or "").strip()
    try:
        parts = s.split(":")
        if len(parts) != 2:
            return None
        h = int(parts[0])
        mi = int(parts[1])
        if not (0 <= h <= 23 and 0 <= mi <= 59):
            return None
        return h * 60 + mi
    except Exception:
        return None

def fmt_min_to_hhmm(m: int) -> str:
    m = int(m)
    h = (m // 60) % 24
    mi = m % 60
    return f"{h:02d}:{mi:02d}"

def normalize_day_windows(day_windows: Optional[List[Dict[str, Any]]], max_days: int = MAX_DAYS) -> List[Dict[str, str]]:
    default = {"start": f"{DAY_START_HOUR:02d}:{DAY_START_MINUTE:02d}", "end": "16:00"}
    out: List[Dict[str, str]] = []
    src = day_windows if isinstance(day_windows, list) else []
    for i in range(int(max_days)):
        w = src[i] if i < len(src) and isinstance(src[i], dict) else {}
        st = str(w.get("start") or "").strip()
        en = str(w.get("end") or "").strip()
        st_ok = parse_hhmm_to_min(st) is not None
        en_ok = parse_hhmm_to_min(en) is not None
        if not (st_ok and en_ok):
            out.append(default.copy())
        else:
            out.append({"start": st, "end": en})
    return out

def day_limits_from_windows(
    day_windows_norm: List[Dict[str, str]],
    fallback_total_limit: int,
    max_days: int = MAX_DAYS
) -> List[int]:
    limits: List[int] = []
    for w in day_windows_norm[:int(max_days)]:
        st = parse_hhmm_to_min(w["start"])
        en = parse_hhmm_to_min(w["end"])
        if st is None or en is None:
            limits.append(int(fallback_total_limit))
            continue
        if en <= st:
            limits.append(int(fallback_total_limit))
            continue
        limits.append(int(en - st))
    return limits


# =======================
# (필수/마감) 유틸
# =======================
def normalize_mandatory_rules_payload(mandatory_rules: Any, max_days: int) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}

    if mandatory_rules is None:
        return out
    if not isinstance(mandatory_rules, dict):
        raise ValueError("mandatory_rules는 객체(JSON dict)여야 합니다.")

    for k, v in mandatory_rules.items():
        try:
            bid = int(k)
        except Exception:
            raise ValueError(f"mandatory_rules key({k})는 정수 bridge_id여야 합니다.")

        if v is None:
            out[bid] = {"required": False, "deadline_day": None}
            continue
        if not isinstance(v, dict):
            raise ValueError(f"mandatory_rules[{k}]는 객체여야 합니다.")

        required = bool(v.get("required", False))

        dd = v.get("deadline_day", None)
        deadline_day: Optional[int] = None
        if dd is not None and dd != "":
            try:
                deadline_day = int(dd)
            except Exception:
                raise ValueError(f"mandatory_rules[{k}].deadline_day는 정수 또는 null이어야 합니다.")
            if deadline_day < 1 or deadline_day > int(max_days):
                raise ValueError(f"mandatory_rules[{k}].deadline_day는 1~{int(max_days)} 범위여야 합니다.")

        if not required:
            deadline_day = None

        out[bid] = {"required": required, "deadline_day": deadline_day}

    return out

def build_mandatory_by_index(
    bridge_rows: List[Dict[str, Any]],
    mandatory_by_bridge_id: Dict[int, Dict[str, Any]],
) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for idx in range(1, len(bridge_rows) + 1):
        b = bridge_rows[idx - 1]
        bid = int(b.get("bridge_id"))
        rule = mandatory_by_bridge_id.get(bid, None) or {}
        required = bool(rule.get("required", False))
        deadline_day = rule.get("deadline_day", None)
        if deadline_day is not None:
            try:
                deadline_day = int(deadline_day)
            except Exception:
                deadline_day = None
        out[idx] = {
            "bridge_id": bid,
            "required": required,
            "deadline_day": deadline_day,
        }
    return out

def compute_mandatory_meta_from_indices(
    *,
    days_idx: List[List[int]],
    unscheduled_indices: List[int],
    mandatory_by_index: Dict[int, Dict[str, Any]],
) -> Dict[str, Any]:
    required_set = set()
    deadline_map: Dict[int, int] = {}
    idx_to_bridge_id: Dict[int, int] = {}

    for idx, rule in (mandatory_by_index or {}).items():
        bid = int(rule.get("bridge_id"))
        idx_to_bridge_id[int(idx)] = bid
        if bool(rule.get("required", False)):
            required_set.add(int(idx))
            dd = rule.get("deadline_day", None)
            if dd is not None:
                try:
                    deadline_map[int(idx)] = int(dd)
                except Exception:
                    pass

    assigned_day: Dict[int, int] = {}
    for di, dnodes in enumerate(days_idx or [], start=1):
        for idx in dnodes or []:
            assigned_day[int(idx)] = int(di)

    required_total = len(required_set)
    required_scheduled_count = 0
    missing_required: List[int] = []
    deadline_violations: List[Dict[str, Any]] = []

    for idx in sorted(required_set):
        if idx not in assigned_day:
            missing_required.append(idx_to_bridge_id.get(idx, -1))
            continue
        required_scheduled_count += 1
        dd = deadline_map.get(idx, None)
        if dd is not None and assigned_day[idx] > dd:
            deadline_violations.append({
                "bridge_id": idx_to_bridge_id.get(idx, -1),
                "assigned_day": int(assigned_day[idx]),
                "deadline_day": int(dd),
            })

    return {
        "required_total": int(required_total),
        "required_scheduled_count": int(required_scheduled_count),
        "required_missing_count": int(len(missing_required)),
        "deadline_violations_count": int(len(deadline_violations)),
        "missing_required_ids": [int(x) for x in missing_required if int(x) > 0],
        "deadline_violations": deadline_violations,
    }


# =======================
# 근사(하버사인) 시간
# =======================
def haversine_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    lat1, lon1 = a
    lat2, lon2 = b
    R = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))

def approx_time_min_from_km(dist_km: float, avg_kmh: float = 30.0) -> int:
    if dist_km <= 0:
        return 0
    minutes = dist_km / avg_kmh * 60.0
    return max(1, int(round(minutes)))

def build_approx_time_mat(points: List[Tuple[float, float]], avg_kmh: float = 30.0) -> List[List[int]]:
    n = len(points)
    mat = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            mat[i][j] = approx_time_min_from_km(haversine_km(points[i], points[j]), avg_kmh=avg_kmh)
    return mat


# =======================
# 실제(카카오) 시간행렬 (i->j 전부) - time_mat 정의용
# =======================
def build_real_time_mat_kakao(
    points: List[Tuple[float, float]],
    cache: Dict[str, Any]
) -> Tuple[List[List[int]], Dict[str, int]]:
    n = len(points)
    mat = [[0] * n for _ in range(n)]

    requested_edges = 0
    cache_hits = 0
    api_calls = 0

    def _is_cache_hit(o: Tuple[float, float], d: Tuple[float, float]) -> bool:
        key = "edge:" + route_cache_key(o, d, coord_round_digits=COORD_ROUND_DIGITS)
        if key not in cache:
            return False
        obj = cache.get(key) or {}
        p = obj.get("path", None)
        return isinstance(p, list) and len(p) >= 2 and int(obj.get("duration_min", 0) or 0) > 0

    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            requested_edges += 1
            o = points[i]
            d = points[j]
            if _is_cache_hit(o, d):
                cache_hits += 1
            else:
                api_calls += 1

            e = kakao_route_edge(
                o, d, cache,
                rest_api_key=KAKAO_REST_API_KEY,
                coord_round_digits=COORD_ROUND_DIGITS,
            )
            mat[i][j] = int(e["duration_min"])

    return mat, {"requested_edges": requested_edges, "cache_hits": cache_hits, "api_calls": api_calls}


# =======================
# (표시용) polyline만 얻기: duration은 절대 사용하지 않음
# =======================
def get_polyline_path_only(
    a: Tuple[float, float],
    b: Tuple[float, float],
    cache: Dict[str, Any],
) -> List[List[float]]:
    try:
        e = kakao_route_edge(
            a, b, cache,
            rest_api_key=KAKAO_REST_API_KEY,
            coord_round_digits=COORD_ROUND_DIGITS,
        )
        p = e.get("path", []) or []
        if isinstance(p, list) and len(p) >= 2:
            return p
    except Exception:
        pass
    return [[float(a[0]), float(a[1])], [float(b[0]), float(b[1])]]


# =======================
# A안 하드제약 시뮬레이션(복귀 포함)
# =======================
def simulate_days_with_final_return_hard(
    start_idx: int,
    days: List[List[int]],
    time_mat: List[List[int]],
    inspect_min: List[int],
    day_limits_total: List[int],
    max_days: int,
    *,
    allow_next_day_for_return: bool = True,
) -> Dict[str, Any]:
    limits = [int(x) for x in (day_limits_total or [])][:max_days]
    if len(limits) < max_days:
        last = limits[-1] if limits else DAY_LIMIT_TOTAL_MIN_DEFAULT
        while len(limits) < max_days:
            limits.append(int(last))

    out_days = [list(map(int, d)) for d in (days or [])]

    feasible = True
    day_totals: List[int] = []
    total_move = 0
    total_insp = 0

    cur_pos = int(start_idx)

    for di, dnodes in enumerate(out_days):
        dm = 0
        dii = 0

        chain = [cur_pos] + dnodes
        for i in range(len(chain) - 1):
            dm += int(time_mat[chain[i]][chain[i + 1]])
        for x in dnodes:
            dii += int(inspect_min[int(x)])

        day_total = int(dm + dii)
        day_totals.append(day_total)
        total_move += int(dm)
        total_insp += int(dii)

        if di < len(limits) and day_total > int(limits[di]):
            feasible = False

        if dnodes:
            cur_pos = int(dnodes[-1])

    return_added = False
    return_day_index: Optional[int] = None
    return_move = 0

    has_any = any(len(d) > 0 for d in out_days)
    if has_any:
        return_move = int(time_mat[cur_pos][int(start_idx)])

        if out_days:
            last_i = len(out_days) - 1
        else:
            last_i = 0
            out_days = [[]]
            day_totals = [0]

        if (day_totals[last_i] + return_move) <= int(limits[last_i]):
            day_totals[last_i] = int(day_totals[last_i] + return_move)
            total_move += int(return_move)
            return_added = True
            return_day_index = last_i
        else:
            if allow_next_day_for_return:
                next_i = last_i + 1
                if next_i < max_days and return_move <= int(limits[next_i]):
                    out_days.append([])
                    day_totals.append(int(return_move))
                    total_move += int(return_move)
                    return_added = True
                    return_day_index = next_i
                else:
                    feasible = False
            else:
                feasible = False

    used_days = int(len(out_days))
    last_day_total = int(day_totals[-1] if day_totals else 0)

    return {
        "feasible": bool(feasible),
        "days": out_days,
        "used_days": int(used_days),
        "total_move": int(total_move),
        "total_insp": int(total_insp),
        "total": int(total_move + total_insp) if feasible else 10**9,
        "max_day_total": int(max(day_totals) if day_totals else 0) if feasible else 10**9,
        "last_day_total": int(last_day_total) if feasible else 10**9,
        "final_return": {
            "required": True,
            "added": bool(return_added),
            "move_min": int(return_move),
            "day_index": int(return_day_index) if return_day_index is not None else None,
            "policy": "same_day_if_fit_else_next_day_return_only_day",
        }
    }


# =======================
# days -> front output
# =======================
def build_front_days_output(
    *,
    days_idx: List[List[int]],
    points: List[Tuple[float, float]],
    time_mat: List[List[int]],
    inspect_min: List[int],
    limits: List[int],
    day_windows_norm: List[Dict[str, str]],
    cache: Dict[str, Any],
    start_idx: int,
    final_return: Dict[str, Any],
    violations: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], int, int, Optional[Dict[str, Any]]]:
    return_added = bool((final_return or {}).get("added", False))
    return_day_index = (final_return or {}).get("day_index", None)
    return_day_1based = int(return_day_index + 1) if isinstance(return_day_index, int) else None

    out_days: List[Dict[str, Any]] = []
    total_move_all = 0
    total_inspect_all = 0
    prev_end_idx = int(start_idx)

    for di, day in enumerate(days_idx, start=1):
        day = day or []
        edges: List[Dict[str, Any]] = []

        day_move = 0
        day_insp = int(sum(int(inspect_min[idx]) for idx in day))

        chain = [prev_end_idx] + day
        for i in range(len(chain) - 1):
            a_idx = int(chain[i])
            b_idx = int(chain[i + 1])
            dur = int(time_mat[a_idx][b_idx])
            day_move += dur

            p = get_polyline_path_only(points[a_idx], points[b_idx], cache)
            edges.append({
                "from_index": int(a_idx),
                "to_index": int(b_idx),
                "duration_min": int(dur),
                "distance_m": 0,
                "path": p,
                "source": "time_mat + kakao_polyline",
            })

        return_edge_obj = None
        if return_added and return_day_1based == di:
            last_pos = int(day[-1]) if day else int(prev_end_idx)
            dur = int(time_mat[last_pos][start_idx])
            day_move += dur

            p = get_polyline_path_only(points[last_pos], points[start_idx], cache)
            return_edge_obj = {
                "day": int(di),
                "from_index": int(last_pos),
                "to_index": int(start_idx),
                "duration_min": int(dur),
                "distance_m": 0,
                "path": p,
                "source": "time_mat + kakao_polyline",
            }
            edges.append(return_edge_obj)

        day_total = int(day_move + day_insp)
        day_limit = int(limits[di - 1]) if (di - 1) < len(limits) else int(limits[-1])

        if day_total > day_limit:
            violations.append({
                "day": int(di),
                "move_min": int(day_move),
                "inspect_min": int(day_insp),
                "total_min": int(day_total),
                "day_limit_total": int(day_limit),
                "reason": "exceeds_day_limit_total_by_time_mat",
            })

        st_txt = (
            day_windows_norm[di - 1]["start"]
            if (di - 1) < len(day_windows_norm)
            else f"{DAY_START_HOUR:02d}:{DAY_START_MINUTE:02d}"
        )
        st_min = parse_hhmm_to_min(st_txt) or (DAY_START_HOUR * 60 + DAY_START_MINUTE)
        end_min = st_min + day_total

        out_days.append({
            "day": int(di),
            "start_time": fmt_min_to_hhmm(st_min),
            "end_time": fmt_min_to_hhmm(end_min),
            "order_index": [int(x) for x in day],
            "move_min": int(day_move),
            "inspect_min": int(day_insp),
            "total_min": int(day_total),
            "day_limit_total": int(day_limit),
            "edges": edges,
        })

        total_move_all += int(day_move)
        total_inspect_all += int(day_insp)

        if day:
            prev_end_idx = int(day[-1])
        if return_edge_obj is not None:
            prev_end_idx = int(start_idx)

    return_to_depot = None
    if return_added and return_day_1based is not None:
        found = None
        for d in out_days:
            if int(d.get("day", -1)) != int(return_day_1based):
                continue
            for e in d.get("edges", []) or []:
                if int(e.get("to_index", -1)) == int(start_idx):
                    found = e
        if found:
            return_to_depot = {
                "day": int(return_day_1based),
                "from_index": int(found["from_index"]),
                "to_index": int(start_idx),
                "duration_min": int(found["duration_min"]),
                "distance_m": int(found.get("distance_m", 0) or 0),
                "path": found.get("path", []) or [],
                "note": "Already included in the corresponding day edges (final return).",
            }

    return out_days, int(total_move_all), int(total_inspect_all), return_to_depot


# =======================
# 스케줄 계산
# =======================
def compute_schedule_no_return(
    points: List[Tuple[float, float]],
    inspect_min: List[int],
    day_limits_total: List[int],
    day_limit_move: int,
    day_windows: Optional[List[Dict[str, str]]] = None,
    max_days: int = MAX_DAYS,
    approx_avg_kmh: float = 30.0,
    do_two_opt: bool = True,
    routing_mode: str = ROUTING_MODE_REAL_MATRIX,
    use_route_cache: bool = True,
    route_cache_path: str = ROUTE_CACHE_PATH,
    multistart_iters: int = 60,
    rnn_k: int = 3,
    seed: int = 42,
    offices_by_index: Optional[List[Optional[str]]] = None,
    mandatory_by_index: Optional[Dict[int, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    start_idx = 0
    n = len(points)
    max_days = int(max_days)
    if max_days < 1:
        max_days = 1
    if max_days > 30:
        max_days = 30

    day_windows_norm = normalize_day_windows(day_windows, max_days=max_days)

    limits = [int(x) for x in (day_limits_total or [])][:max_days]
    if len(limits) < max_days:
        last = limits[-1] if limits else DAY_LIMIT_TOTAL_MIN_DEFAULT
        while len(limits) < max_days:
            limits.append(int(last))

    if n <= 1:
        return {
            "n": int(n),
            "day_limits_total": [int(x) for x in limits],
            "day_limit_move": int(day_limit_move),
            "total_move_min": 0,
            "total_inspect_min": 0,
            "total_min": 0,
            "days": [],
            "unscheduled_indices": [],
            "return_to_depot": None,
            "violations": [],
            "mandatory_meta": compute_mandatory_meta_from_indices(
                days_idx=[],
                unscheduled_indices=[],
                mandatory_by_index=mandatory_by_index or {},
            ),
            "meta": {
                "mode": "empty",
                "routing_mode": routing_mode,
                "approx_avg_kmh": float(approx_avg_kmh),
                "two_opt": bool(do_two_opt),
                "policy": "no_daily_return_mandatory_final_return_hard_constraint",
                "use_route_cache": bool(use_route_cache),
                "route_cache_path": route_cache_path if use_route_cache else None,
                "day_windows": day_windows_norm,
                "max_days": int(max_days),
            }
        }

    mixed_office = False
    office_set: List[str] = []
    if offices_by_index and isinstance(offices_by_index, list) and len(offices_by_index) >= n:
        office_set = sorted({str(x).strip() for x in offices_by_index[1:n] if str(x or "").strip()})
        mixed_office = len(office_set) >= 2

    cache = load_json_cache(route_cache_path) if use_route_cache else {}
    violations: List[Dict[str, Any]] = []

    matrix_stats = {}
    if routing_mode == ROUTING_MODE_REAL_MATRIX:
        try:
            time_mat, matrix_stats = build_real_time_mat_kakao(points, cache)
        except Exception as e:
            routing_mode = ROUTING_MODE_APPROX
            violations.append({
                "day": None,
                "reason": "real_matrix_build_failed_fallback_to_approx",
                "error": str(e),
            })
            time_mat = build_approx_time_mat(points, avg_kmh=approx_avg_kmh)
    else:
        time_mat = build_approx_time_mat(points, avg_kmh=approx_avg_kmh)

    nodes = list(range(1, n))

    # 2-A) 혼합 관할청 => GA
    if mixed_office:
        ga_route, ga_meta = solve_ga_multiday_no_return(
            start_idx=start_idx,
            nodes=nodes,
            time_mat=time_mat,
            inspect_min=inspect_min,
            day_limits_total=limits,
            max_days=max_days,
            seed=seed,
            mandatory_by_index=mandatory_by_index,  # ✅ 추가
        )

        sim = (ga_meta or {}).get("sim", {}) or {}
        days_idx = sim.get("days", []) or []
        unscheduled_indices = [int(x) for x in (sim.get("unscheduled", []) or [])]
        final_return = (sim.get("final_return") or {})

        if not bool(sim.get("feasible", True)):
            violations.append({
                "day": None,
                "reason": "ga_infeasible_fallback_to_heuristics",
                "error": "GA simulation returned infeasible",
            })
        else:
            out_days, total_move_all, total_inspect_all, return_to_depot = build_front_days_output(
                days_idx=days_idx,
                points=points,
                time_mat=time_mat,
                inspect_min=inspect_min,
                limits=limits,
                day_windows_norm=day_windows_norm,
                cache=cache,
                start_idx=start_idx,
                final_return=final_return,
                violations=violations,
            )

            if use_route_cache:
                save_json_cache(route_cache_path, cache)

            meta_mode = (
                "real_matrix_auto_ga_mixed_offices_time_mat_fixed_kakao_polyline_only"
                if routing_mode == ROUTING_MODE_REAL_MATRIX
                else "approx_auto_ga_mixed_offices_time_mat_fixed_kakao_polyline_only"
            )

            mandatory_meta = compute_mandatory_meta_from_indices(
                days_idx=days_idx,
                unscheduled_indices=unscheduled_indices,
                mandatory_by_index=mandatory_by_index or {},
            )

            return {
                "n": int(n),
                "day_limits_total": [int(x) for x in limits],
                "day_limit_move": int(day_limit_move),
                "total_move_min": int(total_move_all),
                "total_inspect_min": int(total_inspect_all),
                "total_min": int(total_move_all + total_inspect_all),
                "days": out_days,
                "unscheduled_indices": [int(x) for x in unscheduled_indices],
                "return_to_depot": return_to_depot,
                "violations": violations,
                "mandatory_meta": mandatory_meta,
                "meta": {
                    "mode": meta_mode,
                    "routing_mode": routing_mode,
                    "approx_avg_kmh": float(approx_avg_kmh),
                    "two_opt": False,
                    "policy": "no_daily_return_mandatory_final_return_hard_constraint_spill_to_next_day",
                    "coord_round_digits": int(COORD_ROUND_DIGITS),
                    "real_matrix_stats": matrix_stats,
                    "use_route_cache": bool(use_route_cache),
                    "route_cache_path": route_cache_path if use_route_cache else None,
                    "day_windows": day_windows_norm,
                    "max_days": int(max_days),
                    "auto_select": {
                        "mixed_office": True,
                        "office_set": office_set,
                        "selected_algo": "ga_multiday_no_return",
                    },
                    "ga": ga_meta,
                    "best_route_preview": {
                        "first_20": [int(x) for x in (ga_route[:20] if ga_route else [])],
                        "length": int(len(ga_route)) if ga_route else 0,
                    }
                }
            }

    # 2-B) 단일 관할청 => 휴리스틱+DP (✅ 여기서 mandatory 하드 제약 적용)
    candidate_routes = make_candidate_routes_multistart(
        start_idx=start_idx,
        nodes=nodes,
        time_mat=time_mat,
        iters=multistart_iters,
        rnn_k=rnn_k,
        seed=seed,
    )

    best_score: Optional[Tuple[int, int, int, int]] = None
    best_route: Optional[List[int]] = None
    best_days_idx: Optional[List[List[int]]] = None
    best_unscheduled: List[int] = []
    best_dp_meta: Optional[Dict[str, Any]] = None
    best_sim: Optional[Dict[str, Any]] = None

    for r in candidate_routes:
        rr = two_opt_chain_from_start(start_idx, r, time_mat) if do_two_opt else r

        # ✅✅✅ (중요) DP split에 mandatory_by_index 전달
        days_try, uns_try, dp_meta = dp_split_days_with_final_return_varlimits(
            global_route=rr,
            inspect_min=inspect_min,
            time_mat=time_mat,
            day_limits_total=limits,
            start_idx=start_idx,
            max_days=max_days,
            fallback_total_limit=DAY_LIMIT_TOTAL_MIN_DEFAULT,
            allow_next_day_for_return=True,
            mandatory_by_index=mandatory_by_index,   # ✅ 하드제약 적용
        )

        # dp가 mandatory infeasible이면 후보 제외(하드제약)
        if dp_meta and dp_meta.get("mandatory_enabled") and not dp_meta.get("mandatory_feasible"):
            continue

        scheduled_count = int(sum(len(x) for x in days_try))
        sim2 = simulate_days_with_final_return_hard(
            start_idx=start_idx,
            days=days_try,
            time_mat=time_mat,
            inspect_min=inspect_min,
            day_limits_total=limits,
            max_days=max_days,
            allow_next_day_for_return=True,
        )

        if not sim2.get("feasible", False):
            continue

        used_days = int(sim2.get("used_days", 10**9))
        last_total = int(sim2.get("last_day_total", 10**9))
        total_move = int(sim2.get("total_move", 10**9))

        score = (-scheduled_count, used_days, last_total, total_move)
        if (best_score is None) or (score < best_score):
            best_score = score
            best_route = rr
            best_days_idx = sim2.get("days", days_try)
            best_unscheduled = uns_try
            best_dp_meta = dp_meta
            best_sim = sim2

    if best_days_idx is None:
        # fallback: NN(+2opt) + dp_split_no_return (✅ 여기에도 mandatory 전달)
        global_route = nearest_neighbor_route_from_start(start_idx, nodes, time_mat)
        if do_two_opt:
            global_route = two_opt_chain_from_start(start_idx, global_route, time_mat)

        days_try, uns_try, dp_meta = dp_split_days_no_return_varlimits(
            global_route=global_route,
            inspect_min=inspect_min,
            time_mat=time_mat,
            day_limits_total=limits,
            start_idx=start_idx,
            max_days=max_days,
            fallback_total_limit=DAY_LIMIT_TOTAL_MIN_DEFAULT,
            mandatory_by_index=mandatory_by_index,   # ✅ 하드제약 적용
        )

        # mandatory infeasible이면 여기서도 실패로 간주
        if dp_meta and dp_meta.get("mandatory_enabled") and not dp_meta.get("mandatory_feasible"):
            return {
                "n": int(n),
                "day_limits_total": [int(x) for x in limits],
                "day_limit_move": int(day_limit_move),
                "total_move_min": 0,
                "total_inspect_min": 0,
                "total_min": 0,
                "days": [],
                "unscheduled_indices": [int(x) for x in global_route],
                "return_to_depot": None,
                "violations": violations + [{
                    "day": None,
                    "reason": "mandatory_infeasible_hard_constraint",
                    "detail": dp_meta,
                }],
                "mandatory_meta": compute_mandatory_meta_from_indices(
                    days_idx=[],
                    unscheduled_indices=[int(x) for x in global_route],
                    mandatory_by_index=mandatory_by_index or {},
                ),
                "meta": {
                    "mode": "mandatory_infeasible",
                    "routing_mode": routing_mode,
                    "approx_avg_kmh": float(approx_avg_kmh),
                    "two_opt": bool(do_two_opt),
                    "policy": "no_daily_return_mandatory_final_return_hard_constraint",
                    "use_route_cache": bool(use_route_cache),
                    "route_cache_path": route_cache_path if use_route_cache else None,
                    "day_windows": day_windows_norm,
                    "max_days": int(max_days),
                    "dp_meta": dp_meta,
                }
            }

        sim2 = simulate_days_with_final_return_hard(
            start_idx=start_idx,
            days=days_try,
            time_mat=time_mat,
            inspect_min=inspect_min,
            day_limits_total=limits,
            max_days=max_days,
            allow_next_day_for_return=True,
        )

        best_route = global_route
        best_days_idx = sim2.get("days", days_try)
        best_unscheduled = uns_try
        best_dp_meta = dp_meta
        best_sim = sim2

        scheduled_count = int(sum(len(x) for x in days_try))
        if sim2.get("feasible", False):
            best_score = (-scheduled_count, int(sim2["used_days"]), int(sim2["last_day_total"]), int(sim2["total_move"]))
        else:
            best_score = None

    days_idx = best_days_idx or []
    sim_final = best_sim or {}
    final_return = sim_final.get("final_return") or {}

    out_days, total_move_all, total_inspect_all, return_to_depot = build_front_days_output(
        days_idx=days_idx,
        points=points,
        time_mat=time_mat,
        inspect_min=inspect_min,
        limits=limits,
        day_windows_norm=day_windows_norm,
        cache=cache,
        start_idx=start_idx,
        final_return=final_return,
        violations=violations,
    )

    if use_route_cache:
        save_json_cache(route_cache_path, cache)

    meta_mode = (
        "real_matrix_multistart_twoopt_dp_split_varlimits_time_mat_fixed_kakao_polyline_only"
        if routing_mode == ROUTING_MODE_REAL_MATRIX
        else "approx_multistart_twoopt_dp_split_varlimits_time_mat_fixed_kakao_polyline_only"
    )

    mandatory_meta_final = compute_mandatory_meta_from_indices(
        days_idx=days_idx,
        unscheduled_indices=(best_unscheduled or []),
        mandatory_by_index=mandatory_by_index or {},
    )

    return {
        "n": int(n),
        "day_limits_total": [int(x) for x in limits],
        "day_limit_move": int(day_limit_move),
        "total_move_min": int(total_move_all),
        "total_inspect_min": int(total_inspect_all),
        "total_min": int(total_move_all + total_inspect_all),
        "days": out_days,
        "unscheduled_indices": [int(x) for x in (best_unscheduled or [])],
        "return_to_depot": return_to_depot,
        "violations": violations,
        "mandatory_meta": mandatory_meta_final,
        "meta": {
            "mode": meta_mode,
            "routing_mode": routing_mode,
            "approx_avg_kmh": float(approx_avg_kmh),
            "two_opt": bool(do_two_opt),
            "policy": "no_daily_return_mandatory_final_return_hard_constraint_spill_to_next_day",
            "coord_round_digits": int(COORD_ROUND_DIGITS),
            "real_matrix_stats": matrix_stats,
            "use_route_cache": bool(use_route_cache),
            "route_cache_path": route_cache_path if use_route_cache else None,
            "day_windows": day_windows_norm,
            "max_days": int(max_days),
            "auto_select": {
                "mixed_office": False,
                "office_set": office_set,
                "selected_algo": "heuristics_multistart_dp_split",
            },
            "multistart": {
                "iters": int(multistart_iters),
                "rnn_k": int(rnn_k),
                "seed": int(seed),
                "best_score": best_score,
                "dp_meta": best_dp_meta,
                "sim_with_return": sim_final,
            },
            "final_return": final_return,
            "mandatory": {
                "enabled": True,
                "hard_constraint": True,
                "note": "DP split enforces required + deadline_day. Infeasible candidates are dropped.",
            },
            "best_route_preview": {
                "first_20": [int(x) for x in (best_route[:20] if best_route else [])],
                "length": int(len(best_route)) if best_route else 0,
            }
        }
    }


# =======================
# Flask Routes
# =======================
@app.route("/")
def root():
    return render_template(
        "index.html",
        KAKAO_JS_API_KEY=CONFIG.get("KAKAO_JS_API_KEY", ""),
    )


def load_bridge_db_with_ids() -> pd.DataFrame:
    df = load_bridge_database(BRIDGE_DB_PATH, REGISTRY_PATH)
    return df


@app.get("/api/bridges")
def api_bridges():
    cache = load_geocode_cache()

    df = load_bridge_database(BRIDGE_DB_PATH, REGISTRY_PATH)
    df = hydrate_latlng_from_cache(df, cache)

    items = []
    for _, r in df.iterrows():
        items.append({
            "bridge_id": int(r["bridge_id"]),
            "office": str(r.get("office", "")).strip(),
            "bridge_name": str(r.get("bridge_name", "")).strip(),
            "address": str(r.get("address", "")).strip(),
            "inspect_min": int(r.get("inspect_min") or 60),
            "lat": float(r["lat"]) if pd.notna(r.get("lat")) else None,
            "lng": float(r["lng"]) if pd.notna(r.get("lng")) else None,
        })

    return jsonify({"items": items, "total": len(items)})


@app.post("/api/resolve_coords")
def api_resolve_coords():
    payload = request.get_json(force=True, silent=True) or {}
    addresses = payload.get("addresses", [])
    if not isinstance(addresses, list):
        return jsonify({"error": "addresses must be a list"}), 400

    cache = load_geocode_cache()
    resolved = {}
    updated = False

    for addr in addresses:
        addr = (addr or "").strip()
        if not addr:
            continue

        if addr in cache and isinstance(cache[addr], dict) and "lat" in cache[addr] and "lng" in cache[addr]:
            resolved[addr] = {"lat": cache[addr]["lat"], "lng": cache[addr]["lng"]}
            continue

        try:
            lat, lng = kakao_geocode(
                addr,
                rest_api_key=KAKAO_REST_API_KEY,
                geocode_cache_path=GEOCODE_CACHE_PATH,
            )
            cache[addr] = {"lat": lat, "lng": lng}
            resolved[addr] = {"lat": lat, "lng": lng}
            updated = True
        except Exception:
            resolved[addr] = None

    if updated:
        save_geocode_cache(cache)

    return jsonify({"coords": resolved})


@app.route("/api/geocode", methods=["GET"])
def api_geocode():
    q = (request.args.get("query") or "").strip()
    if not q:
        return jsonify({"error": "query is required"}), 400

    try:
        lat, lng = kakao_geocode(
            q,
            rest_api_key=KAKAO_REST_API_KEY,
            geocode_cache_path=GEOCODE_CACHE_PATH,
        )
        return jsonify({"lat": lat, "lng": lng})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/offices")
def api_offices():
    df = load_bridge_database(BRIDGE_DB_PATH, REGISTRY_PATH)
    if "office" not in df.columns:
        return jsonify({"items": []})
    offices = sorted([o for o in df["office"].unique().tolist() if str(o).strip() != ""])
    return jsonify({"items": offices})


@app.route("/api/optimize_selected", methods=["POST"])
def api_optimize_selected():
    payload = request.get_json(force=True, silent=True) or {}

    depot_address = (payload.get("depot_address") or "").strip()
    if not depot_address:
        return jsonify({"error": "depot_address가 필요합니다."}), 400

    try:
        max_days = int(payload.get("max_days", MAX_DAYS) or MAX_DAYS)
    except Exception:
        return jsonify({"error": "max_days는 정수여야 합니다."}), 400
    if not (1 <= max_days <= 30):
        return jsonify({"error": "max_days는 1~30 범위여야 합니다."}), 400

    selected_ids = payload.get("selected_bridge_ids", [])
    if not isinstance(selected_ids, list) or len(selected_ids) == 0:
        return jsonify({"error": "selected_bridge_ids가 필요합니다."}), 400

    day_windows_in = payload.get("day_windows_json", None)
    day_windows_norm = normalize_day_windows(day_windows_in, max_days=max_days)

    try:
        day_limit_total_fallback = int(payload.get("day_limit_total_min", DAY_LIMIT_TOTAL_MIN_DEFAULT))
        day_limit_move = int(payload.get("day_limit_move_min", DAY_LIMIT_MOVE_MIN_DEFAULT))
    except Exception:
        return jsonify({"error": "day_limit_total_min / day_limit_move_min 은 정수여야 합니다."}), 400

    day_limits_total = day_limits_from_windows(day_windows_norm, fallback_total_limit=day_limit_total_fallback, max_days=max_days)
    day_limits_total = [int(x) for x in (day_limits_total or [])][:max_days]

    routing_mode = (payload.get("routing_mode") or ROUTING_MODE_REAL_MATRIX).strip().lower()
    if routing_mode not in (ROUTING_MODE_APPROX, ROUTING_MODE_REAL_MATRIX):
        return jsonify({"error": f"routing_mode는 '{ROUTING_MODE_APPROX}' 또는 '{ROUTING_MODE_REAL_MATRIX}' 이어야 합니다."}), 400

    use_route_cache_raw = str(payload.get("use_route_cache", True)).strip().lower()
    use_route_cache = use_route_cache_raw not in ("0", "false", "no", "n")

    route_cache_path = normalize_route_cache_path(payload.get("route_cache_path"))

    try:
        approx_avg_kmh = float(payload.get("approx_avg_kmh", 30.0) or 30.0)
    except Exception:
        approx_avg_kmh = 30.0

    do_two_opt_raw = str(payload.get("do_two_opt", True)).strip().lower()
    do_two_opt = do_two_opt_raw not in ("0", "false", "no", "n")

    multistart_iters = int(payload.get("multistart_iters", 60) or 60)
    rnn_k = int(payload.get("rnn_k", 3) or 3)
    seed = int(payload.get("seed", 42) or 42)

    use_bulk_raw = str(payload.get("use_bulk_inspect", False)).strip().lower()
    use_bulk = use_bulk_raw in ("1", "true", "yes", "y", "on")
    bulk_min = payload.get("bulk_inspect_min", None)
    if use_bulk:
        try:
            bulk_min = int(bulk_min)
            if bulk_min <= 0:
                return jsonify({"error": "bulk_inspect_min은 1 이상의 정수여야 합니다."}), 400
        except Exception:
            return jsonify({"error": "bulk_inspect_min은 정수여야 합니다."}), 400
    else:
        bulk_min = None

    inspect_overrides = payload.get("inspect_overrides", None)
    if inspect_overrides is None:
        inspect_overrides = {}
    if not isinstance(inspect_overrides, dict):
        return jsonify({"error": "inspect_overrides는 객체(JSON dict)여야 합니다."}), 400
    overrides_norm = {}
    for k, v in inspect_overrides.items():
        try:
            bid_k = int(k)
            mv = int(v)
            if mv <= 0:
                return jsonify({"error": f"inspect_overrides[{k}]는 1 이상의 정수여야 합니다."}), 400
            overrides_norm[bid_k] = mv
        except Exception:
            return jsonify({"error": f"inspect_overrides[{k}] 값이 올바르지 않습니다."}), 400

    mandatory_rules_raw = payload.get("mandatory_rules", None)
    try:
        mandatory_by_bridge_id = normalize_mandatory_rules_payload(mandatory_rules_raw, max_days=max_days)
    except Exception as e:
        return jsonify({"error": f"mandatory_rules 값이 올바르지 않습니다: {e}"}), 400

    try:
        depot_lat, depot_lng = kakao_geocode(
            depot_address,
            rest_api_key=KAKAO_REST_API_KEY,
            geocode_cache_path=GEOCODE_CACHE_PATH,
        )
    except Exception as e:
        return jsonify({"error": f"Depot 지오코딩 실패: {e}"}), 500

    try:
        bridge_db_raw = load_bridge_database(BRIDGE_DB_PATH, REGISTRY_PATH)
    except Exception as e:
        return jsonify({"error": f"bridge_database.xlsx 로드 실패: {e}"}), 500

    selected_set = set()
    for x in selected_ids:
        try:
            selected_set.add(int(x))
        except Exception:
            pass

    picked = bridge_db_raw[bridge_db_raw["bridge_id"].astype(int).isin(selected_set)].copy()
    if len(picked) == 0:
        return jsonify({"error": "선택된 bridge_id에 해당하는 교량을 DB에서 찾지 못했습니다."}), 400

    cache = load_geocode_cache()
    picked = hydrate_latlng_from_cache(picked, cache)

    bridge_rows = []
    points = [(float(depot_lat), float(depot_lng))]
    inspect_list = [0]
    skipped = []

    for _, r in picked.iterrows():
        name = str(r.get("bridge_name","")).strip()
        addr = str(r.get("address","")).strip()
        office = str(r.get("office","")).strip()
        bid = int(r["bridge_id"])

        try:
            base_insp = int(r.get("inspect_min", DEFAULT_INSPECT_MIN) or DEFAULT_INSPECT_MIN)
        except Exception:
            base_insp = int(DEFAULT_INSPECT_MIN)
        if base_insp <= 0:
            base_insp = int(DEFAULT_INSPECT_MIN)

        insp = base_insp
        if use_bulk and bulk_min is not None:
            insp = int(bulk_min)
        if bid in overrides_norm:
            insp = int(overrides_norm[bid])

        lat = r.get("lat", None)
        lng = r.get("lng", None)

        if pd.notna(lat) and pd.notna(lng):
            lat, lng = float(lat), float(lng)
        else:
            try:
                lat, lng = kakao_geocode(
                    addr,
                    rest_api_key=KAKAO_REST_API_KEY,
                    geocode_cache_path=GEOCODE_CACHE_PATH,
                )
            except Exception as e:
                skipped.append({"bridge_id": bid, "bridge_name": name, "address": addr, "reason": str(e)})
                continue

        rule = mandatory_by_bridge_id.get(bid, None) or {}
        required = bool(rule.get("required", False))
        deadline_day = rule.get("deadline_day", None)
        if deadline_day is not None:
            try:
                deadline_day = int(deadline_day)
            except Exception:
                deadline_day = None

        bridge_rows.append({
            "bridge_id": bid,
            "office": office,
            "bridge_name": name,
            "address": addr,
            "inspect_min": int(insp),
            "lat": float(lat),
            "lng": float(lng),
            "required": bool(required),
            "deadline_day": int(deadline_day) if deadline_day is not None else None,
        })
        points.append((float(lat), float(lng)))
        inspect_list.append(int(insp))

    if len(points) <= 1:
        return jsonify({"error": "선택 교량의 좌표 확보에 전부 실패했습니다.", "skipped": skipped}), 400

    offices_by_index = [None] + [str(b.get("office", "")).strip() for b in bridge_rows]
    mandatory_by_index = build_mandatory_by_index(bridge_rows, mandatory_by_bridge_id)

    try:
        schedule = compute_schedule_no_return(
            points=points,
            inspect_min=inspect_list,
            day_limits_total=day_limits_total,
            day_limit_move=day_limit_move,
            day_windows=day_windows_norm,
            max_days=max_days,
            approx_avg_kmh=approx_avg_kmh,
            do_two_opt=do_two_opt,
            routing_mode=routing_mode,
            use_route_cache=use_route_cache,
            route_cache_path=route_cache_path,
            multistart_iters=multistart_iters,
            rnn_k=rnn_k,
            seed=seed,
            offices_by_index=offices_by_index,
            mandatory_by_index=mandatory_by_index,   # ✅ 전달
        )
    except Exception as e:
        return jsonify({"error": f"최적화 계산 실패: {e}"}), 500

    for day in schedule.get("days", []):
        order = []
        for idx in day.get("order_index", []):
            order.append(bridge_rows[idx - 1])
        day["order"] = order

    unscheduled = []
    for idx in schedule.get("unscheduled_indices", []):
        if idx <= 0:
            continue
        bi = idx - 1
        if 0 <= bi < len(bridge_rows):
            unscheduled.append(bridge_rows[bi])
    schedule["unscheduled"] = unscheduled

    offices = sorted({str(b.get("office","")).strip() for b in bridge_rows if str(b.get("office","")).strip()})

    return jsonify({
        "depot": {"address": depot_address, "lat": depot_lat, "lng": depot_lng},
        "schedule": schedule,
        "bridges": bridge_rows,
        "unscheduled": unscheduled,
        "skipped": skipped,
        "input_options": {
            "day_windows": day_windows_norm,
            "day_limits_total": [int(x) for x in day_limits_total],
            "use_bulk_inspect": bool(use_bulk),
            "bulk_inspect_min": int(bulk_min) if bulk_min is not None else None,
            "inspect_overrides": {str(k): int(v) for k, v in overrides_norm.items()},
            "max_days": int(max_days),
            "offices": offices,
            "mandatory_rules": {str(k): v for k, v in mandatory_by_bridge_id.items()},
        }
    })


@app.route("/api/optimize", methods=["POST"])
def api_optimize():
    # (기존 업로드 기반 optimize는 그대로 유지: mandatory_rules 미지원)
    print(">>> /api/optimize called", flush=True)
    return jsonify({"error": "업로드 기반 /api/optimize는 현재 mandatory_rules 미지원입니다. /api/optimize_selected를 사용하세요."}), 400


if __name__ == "__main__":
    import threading
    import webbrowser

    host = "127.0.0.1"
    port = 8000
    url = f"http://{host}:{port}/"

    if not KAKAO_REST_API_KEY or KAKAO_REST_API_KEY.startswith("PUT_YOUR"):
        print("WARNING: KAKAO_REST_API_KEY가 비어있습니다. (지오코딩/길찾기 모두 동작 불가)", flush=True)

    def _open_browser():
        try:
            webbrowser.open(url, new=1)
        except Exception as e:
            print(f"브라우저 자동 열기 실패: {e}", flush=True)

    threading.Timer(1.0, _open_browser).start()

    app.run(
        host=host,
        port=port,
        debug=False,
        use_reloader=False,
        threaded=True,
    )
