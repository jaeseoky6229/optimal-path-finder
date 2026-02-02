# services/kakao_client.py
from typing import Dict, Any, Tuple, List

import requests

from .cache_utils import load_json_cache, save_json_cache, route_cache_key


KAKAO_GEOCODE_URL_DEFAULT = "https://dapi.kakao.com/v2/local/search/address.json"
KAKAO_MOBILITY_DIRECTIONS_URL_DEFAULT = "https://apis-navi.kakaomobility.com/v1/directions"


def _kakao_headers(rest_api_key: str) -> Dict[str, str]:
    if not rest_api_key or rest_api_key.startswith("PUT_YOUR"):
        raise RuntimeError("KAKAO_REST_API_KEY가 설정되어 있지 않습니다.")
    return {"Authorization": f"KakaoAK {rest_api_key}"}


def kakao_geocode(
    address: str,
    *,
    rest_api_key: str,
    geocode_cache_path: str,
    geocode_url: str = KAKAO_GEOCODE_URL_DEFAULT,
    timeout_sec: int = 10,
) -> Tuple[float, float]:
    """
    address -> (lat,lng)
    geocode_cache_path에 주소별 lat/lng 캐시 저장
    """
    address = str(address or "").strip()
    if not address:
        raise ValueError("지오코딩 실패: 빈 address")

    geocache = load_json_cache(geocode_cache_path)
    if address in geocache:
        try:
            lat = float(geocache[address]["lat"])
            lng = float(geocache[address]["lng"])
            return (lat, lng)
        except Exception:
            pass

    headers = _kakao_headers(rest_api_key)
    params = {"query": address}

    r = requests.get(geocode_url, headers=headers, params=params, timeout=timeout_sec)
    r.raise_for_status()
    data = r.json()

    docs = data.get("documents", [])
    if not docs:
        raise ValueError(f"지오코딩 실패: {address}")

    x = float(docs[0]["x"])  # lng
    y = float(docs[0]["y"])  # lat

    geocache[address] = {"lat": y, "lng": x}
    save_json_cache(geocode_cache_path, geocache)

    return (y, x)


def _extract_path_latlng_from_directions(data: Dict[str, Any]) -> List[List[float]]:
    """
    Kakao mobility directions 응답에서 path(좌표열)를 추출.
    반환: [[lat,lng], ...]
    """
    routes = data.get("routes", [])
    if not routes:
        return []

    sections = routes[0].get("sections", [])
    path: List[List[float]] = []

    for sec in sections:
        roads = sec.get("roads", [])
        for road in roads:
            vertexes = road.get("vertexes", [])
            # vertexes = [x1,y1,x2,y2,...] (x=lng, y=lat)
            for i in range(0, len(vertexes) - 1, 2):
                lng = float(vertexes[i])
                lat = float(vertexes[i + 1])
                path.append([lat, lng])

    # 연속 중복 제거
    if not path:
        return path
    compact = [path[0]]
    for p in path[1:]:
        if p[0] != compact[-1][0] or p[1] != compact[-1][1]:
            compact.append(p)
    return compact


def kakao_route_edge(
    origin: Tuple[float, float],
    dest: Tuple[float, float],
    cache: Dict[str, Any],
    *,
    rest_api_key: str,
    coord_round_digits: int = 6,
    directions_url: str = KAKAO_MOBILITY_DIRECTIONS_URL_DEFAULT,
    timeout_sec: int = 20,
) -> Dict[str, Any]:
    """
    엣지(연속 구간) 단위 호출/캐시.
    - origin/dest: (lat,lng)
    - cache: route_cache.json을 load한 dict(상위에서 주입)
    반환:
      {
        "duration_min": int,
        "distance_m": int,
        "path": [[lat,lng], ...]
      }
    """
    if origin == dest:
        return {"duration_min": 0, "distance_m": 0, "path": [[origin[0], origin[1]]]}

    key = "edge:" + route_cache_key(origin, dest, coord_round_digits=coord_round_digits)

    # 캐시가 있어도 path가 없거나 너무 짧으면(구버전 캐시) 재조회
    if key in cache:
        obj = cache[key] or {}
        cached_path = obj.get("path", None)
        if isinstance(cached_path, list) and len(cached_path) >= 2:
            return {
                "duration_min": int(obj.get("duration_min", 0) or 0),
                "distance_m": int(obj.get("distance_m", 0) or 0),
                "path": cached_path,
            }

    headers = _kakao_headers(rest_api_key)
    params = {
        "origin": f"{origin[1]},{origin[0]}",
        "destination": f"{dest[1]},{dest[0]}",
        "priority": "RECOMMEND",
        "alternatives": "false",
        "road_details": "true",  # 폴리라인 추출
    }

    r = requests.get(directions_url, headers=headers, params=params, timeout=timeout_sec)
    r.raise_for_status()
    data = r.json()

    routes = data.get("routes", [])
    if not routes:
        raise ValueError("경로 없음(모빌리티 응답 routes 비어있음)")

    summary = routes[0].get("summary", {})
    duration_sec = int(summary.get("duration", 0))
    distance_m = int(summary.get("distance", 0))

    if duration_sec <= 0:
        raise ValueError("경로 시간 파싱 실패(summary.duration이 0)")

    duration_min = max(1, int(round(duration_sec / 60)))
    path = _extract_path_latlng_from_directions(data)

    cache[key] = {
        "duration_min": int(duration_min),
        "distance_m": int(distance_m),
        "path": path,
    }
    return {"duration_min": int(duration_min), "distance_m": int(distance_m), "path": path}
