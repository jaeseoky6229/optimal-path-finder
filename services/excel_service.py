import json
import os
from dataclasses import dataclass
from typing import Dict, Tuple, Optional, List

import pandas as pd


@dataclass
class BridgeRecord:
    bridge_id: int
    bridge_name: str
    address: str
    lat: Optional[float]
    lng: Optional[float]
    inspect_min: Optional[int]
    office: str


def _safe_str(x) -> str:
    if x is None:
        return ""
    return str(x).strip()


def _safe_int(x) -> Optional[int]:
    if x is None:
        return None
    s = str(x).strip()
    if s == "":
        return None
    try:
        return int(float(s))
    except Exception:
        return None


def _safe_float(x) -> Optional[float]:
    if x is None:
        return None
    s = str(x).strip()
    if s == "":
        return None
    try:
        return float(s)
    except Exception:
        return None


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    # 엑셀 컬럼명 표준화
    rename_map = {}

    for c in df.columns:
        cc = str(c).strip()

        if cc in ["bridge_name", "교량명", "교량 이름", "교량"]:
            rename_map[c] = "bridge_name"
        elif cc in ["address", "주소", "소재지", "위치", "소재지주소"]:
            rename_map[c] = "address"
        elif cc in ["lat", "위도", "latitude"]:
            rename_map[c] = "lat"
        elif cc in ["lng", "경도", "lon", "longitude"]:
            rename_map[c] = "lng"
        elif cc in ["inspect_min", " inspect_min", "점검시간", "점검_분", "inspect time", "inspectmin"]:
            rename_map[c] = "inspect_min"
        elif cc in ["관할", "office", "관리청", "관할청"]:
            rename_map[c] = "office"

    df = df.rename(columns=rename_map)

    # ✅ 필수 컬럼: office는 더 이상 필수가 아님(없으면 '없음'으로 생성)
    required = ["bridge_name", "address", "inspect_min"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"엑셀에 필수 컬럼이 없습니다: {missing} "
            f"(현재 컬럼: {list(df.columns)})"
        )

    # ✅ office 컬럼이 없으면 생성 + 기본값 '없음'
    if "office" not in df.columns:
        df["office"] = "없음"

    # 없는 선택 컬럼은 생성
    if "lat" not in df.columns:
        df["lat"] = None
    if "lng" not in df.columns:
        df["lng"] = None

    # 공백/NaN 정리
    df["bridge_name"] = df["bridge_name"].apply(_safe_str)
    df["address"] = df["address"].apply(_safe_str)

    # ✅ office: 비어있으면 '없음'으로 분류
    df["office"] = df["office"].apply(_safe_str)
    df.loc[df["office"] == "", "office"] = "없음"

    df["inspect_min"] = df["inspect_min"].apply(_safe_int)
    df["lat"] = df["lat"].apply(_safe_float)
    df["lng"] = df["lng"].apply(_safe_float)

    # 완전 빈 행 제거(교량명+주소+관할 모두 비면 제거)
    df = df[~((df["bridge_name"] == "") & (df["address"] == "") & (df["office"] == ""))].copy()

    return df



def _natural_key(office: str, bridge_name: str, address: str) -> str:
    # “같은 교량인지”를 판단하기 위한 키 (레지스트리 키)
    # 주소 표기 흔들림이 심하면 여기에서 정규화 규칙을 더 넣을 수 있음.
    return f"{office}|{bridge_name}|{address}"


def load_registry(registry_path: str) -> Dict[str, int]:
    if not os.path.exists(registry_path):
        return {}
    with open(registry_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # 값이 int가 아니면 무시/정리
    cleaned = {}
    for k, v in (data or {}).items():
        try:
            cleaned[str(k)] = int(v)
        except Exception:
            continue
    return cleaned


def save_registry(registry_path: str, registry: Dict[str, int]) -> None:
    os.makedirs(os.path.dirname(registry_path), exist_ok=True)
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)


def assign_bridge_ids(
    df: pd.DataFrame,
    registry_path: str,
) -> Tuple[pd.DataFrame, Dict[str, int]]:
    registry = load_registry(registry_path)
    next_id = (max(registry.values()) + 1) if registry else 0

    bridge_ids: List[int] = []
    updated = False

    for _, row in df.iterrows():
        office = _safe_str(row.get("office"))
        name = _safe_str(row.get("bridge_name"))
        addr = _safe_str(row.get("address"))
        key = _natural_key(office, name, addr)

        if key in registry:
            bid = registry[key]
        else:
            bid = next_id
            registry[key] = bid
            next_id += 1
            updated = True

        bridge_ids.append(bid)

    df = df.copy()
    df["bridge_id"] = bridge_ids

    if updated:
        save_registry(registry_path, registry)

    # 혹시라도 중복 id가 생기는지 최종 검증
    if df["bridge_id"].isna().any():
        raise ValueError("bridge_id 생성에 실패한 행이 있습니다.")
    if df["bridge_id"].duplicated().any():
        # 이 경우는 registry가 꼬였거나 자연키가 잘못됐을 때
        dup = df[df["bridge_id"].duplicated(keep=False)][["bridge_id", "office", "bridge_name", "address"]]
        raise ValueError(f"bridge_id 중복 발생 (레지스트리/자연키 확인 필요)\n{dup.to_string(index=False)}")

    return df, registry


def load_bridge_database(
    excel_path: str,
    registry_path: str,
) -> pd.DataFrame:
    df = pd.read_excel(excel_path, sheet_name=0)
    df = normalize_columns(df)
    df, _ = assign_bridge_ids(df, registry_path)

    # 정렬은 “표시용”일 뿐, id는 registry로 고정됨 (정렬해도 문제 없음)
    df = df.sort_values(by=["office", "bridge_name", "address"], kind="stable").reset_index(drop=True)
    return df


def to_bridge_records(df: pd.DataFrame) -> List[BridgeRecord]:
    out: List[BridgeRecord] = []
    for _, r in df.iterrows():
        out.append(
            BridgeRecord(
                bridge_id=int(r["bridge_id"]),
                bridge_name=_safe_str(r["bridge_name"]),
                address=_safe_str(r["address"]),
                lat=_safe_float(r.get("lat")),
                lng=_safe_float(r.get("lng")),
                inspect_min=_safe_int(r.get("inspect_min")),
                office=_safe_str(r.get("office")),
            )
        )
    return out
