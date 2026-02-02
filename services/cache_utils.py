# services/cache_utils.py
import os
import json
import hashlib
from typing import Dict, Any, Tuple

# 좌표 캐시 키 rounding 자리수 (합의: 5~6자리 충분)
COORD_ROUND_DIGITS_DEFAULT = 6


def load_json_cache(path: str) -> Dict[str, Any]:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def save_json_cache(path: str, cache: Dict[str, Any]) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def route_cache_key(
    origin: Tuple[float, float],
    dest: Tuple[float, float],
    coord_round_digits: int = COORD_ROUND_DIGITS_DEFAULT,
) -> str:
    # origin,dest = (lat,lng)
    s = (
        f"{round(origin[0], coord_round_digits)},{round(origin[1], coord_round_digits)}"
        f"->{round(dest[0], coord_round_digits)},{round(dest[1], coord_round_digits)}"
    )
    return hashlib.md5(s.encode("utf-8")).hexdigest()

