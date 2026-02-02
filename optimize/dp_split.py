from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


INF = 10**18


def _safe_int(x, default=None):
    try:
        return int(x)
    except Exception:
        return default


def _normalize_limits(day_limits_total: List[int], max_days: int, fallback_total_limit: int) -> List[int]:
    limits = [int(x) for x in (day_limits_total or [])][: int(max_days)]
    if len(limits) < int(max_days):
        last = limits[-1] if limits else int(fallback_total_limit)
        while len(limits) < int(max_days):
            limits.append(int(last))
    return limits


def _mandatory_required_set(mandatory_by_index: Optional[Dict[int, Dict[str, Any]]]) -> set:
    req = set()
    if not mandatory_by_index:
        return req
    for idx, r in mandatory_by_index.items():
        if bool((r or {}).get("required", False)):
            req.add(int(idx))
    return req


def _mandatory_deadline_map(mandatory_by_index: Optional[Dict[int, Dict[str, Any]]]) -> Dict[int, int]:
    mp: Dict[int, int] = {}
    if not mandatory_by_index:
        return mp
    for idx, r in mandatory_by_index.items():
        if not bool((r or {}).get("required", False)):
            continue
        dd = (r or {}).get("deadline_day", None)
        if dd is None or dd == "":
            continue
        ddi = _safe_int(dd, None)
        if ddi is None:
            continue
        mp[int(idx)] = int(ddi)
    return mp


def _filter_route_required_only(
    global_route: List[int],
    mandatory_by_index: Optional[Dict[int, Dict[str, Any]]],
) -> List[int]:
    req = _mandatory_required_set(mandatory_by_index)
    if not req:
        return list(global_route or [])
    return [int(x) for x in (global_route or []) if int(x) in req]


def _build_required_interval_min_deadline(
    route_nodes: List[int],
    deadline_map: Dict[int, int],
) -> List[List[int]]:
    """
    min_deadline_in_interval[i][j] (inclusive i..j over route_nodes indices)
    - interval에 required 노드가 없으면 +INF
    """
    m = len(route_nodes)
    out = [[INF] * m for _ in range(m)]
    for i in range(m):
        cur = INF
        for j in range(i, m):
            nd = int(route_nodes[j])
            if nd in deadline_map:
                cur = min(cur, int(deadline_map[nd]))
            out[i][j] = cur
    return out


def _prefix_inspect(inspect_min: List[int], route_nodes: List[int]) -> List[int]:
    """
    route_nodes는 points index(1..). inspect_min은 points index로 접근 가능.
    """
    pref = [0]
    s = 0
    for nd in route_nodes:
        s += int(inspect_min[int(nd)])
        pref.append(s)
    return pref  # len = m+1


def _prefix_consec_move(time_mat: List[List[int]], route_nodes: List[int]) -> List[int]:
    """
    route_nodes[0] -> route_nodes[1] -> ... 연속 이동 누적합
    consec_pref[k] = sum_{t=1..k} time(route[t-1], route[t]) for k in [0..m-1] with consec_pref[0]=0
    so internal move i..j = consec_pref[j] - consec_pref[i]
    """
    m = len(route_nodes)
    pref = [0] * m
    acc = 0
    for k in range(1, m):
        acc += int(time_mat[int(route_nodes[k - 1])][int(route_nodes[k])])
        pref[k] = acc
    return pref  # len=m


def _segment_total_no_return(
    *,
    start_idx: int,
    route_nodes: List[int],
    i: int,
    j: int,
    time_mat: List[List[int]],
    inspect_pref: List[int],
    consec_move_pref: List[int],
) -> int:
    """
    day segment = route_nodes[i..j] (inclusive)
    no_daily_return 정책: day 시작 위치는 (i==0 ? start_idx : route_nodes[i-1]) 라고 가정
    """
    if i > j:
        return 0

    prev_end = int(start_idx) if i == 0 else int(route_nodes[i - 1])
    first = int(route_nodes[i])

    move = int(time_mat[prev_end][first])
    if i < j:
        move += int(consec_move_pref[j] - consec_move_pref[i])

    insp = int(inspect_pref[j + 1] - inspect_pref[i])
    return int(move + insp)


def _dp_split_route_with_mandatory(
    *,
    global_route: List[int],
    inspect_min: List[int],
    time_mat: List[List[int]],
    day_limits_total: List[int],
    start_idx: int,
    max_days: int,
    fallback_total_limit: int,
    mandatory_by_index: Optional[Dict[int, Dict[str, Any]]] = None,
) -> Tuple[List[List[int]], List[int], Dict[str, Any]]:
    """
    global_route: 방문 순서(노드 index들의 리스트, start_idx는 포함하지 않는다고 가정)
    반환:
      - days: List[List[int]]  (각 day에 배정된 노드 index)
      - unscheduled: List[int] (배정되지 않은 노드 index)
      - meta: Dict
    """
    route_nodes = [int(x) for x in (global_route or [])]
    m = len(route_nodes)

    limits = _normalize_limits(day_limits_total, max_days=max_days, fallback_total_limit=fallback_total_limit)

    required_set = _mandatory_required_set(mandatory_by_index)
    deadline_map = _mandatory_deadline_map(mandatory_by_index)

    # required가 route에 없으면(데이터 불일치) -> infeasible
    missing_in_route = sorted([x for x in required_set if x not in set(route_nodes)])
    if missing_in_route:
        return [], route_nodes[:], {
            "mode": "dp_split_mandatory",
            "mandatory_feasible": False,
            "reason": "required_nodes_missing_in_route",
            "missing_required_indices": missing_in_route,
        }

    # required 노드가 하나도 없으면 기존처럼 "최대한 많이(=전부)" 배치하는 것이 목적
    mandatory_enabled = bool(required_set)

    # DP 준비
    inspect_pref = _prefix_inspect(inspect_min, route_nodes)
    consec_move_pref = _prefix_consec_move(time_mat, route_nodes)

    # 마감 제약: interval(i..j)에 포함된 required들의 최소 deadline
    min_deadline_in_interval = _build_required_interval_min_deadline(route_nodes, deadline_map) if mandatory_enabled else None

    # dp[day][pos] = (cost, prev_pos) ; pos는 0..m (처리한 prefix 길이)
    # cost는 여기서는 "총 소요시간"을 최소화로 두되, 최종 선택은 "가장 큰 pos" 우선으로 함
    dp_cost = [[INF] * (m + 1) for _ in range(max_days + 1)]
    dp_prev = [[None] * (m + 1) for _ in range(max_days + 1)]

    dp_cost[0][0] = 0

    # 필수/마감 체크를 위한: route position -> required 여부/마감
    # segment가 day=t에 배정될 때 interval 내 required들은 deadline >= t 이어야 함
    for day in range(1, max_days + 1):
        limit = int(limits[day - 1])

        for j in range(1, m + 1):  # prefix length
            best_c = INF
            best_i = None

            # i = 이전 prefix length, segment covers [i..j-1]
            for i in range(0, j):
                if dp_cost[day - 1][i] >= INF:
                    continue

                # segment total
                seg_total = _segment_total_no_return(
                    start_idx=start_idx,
                    route_nodes=route_nodes,
                    i=i,
                    j=j - 1,
                    time_mat=time_mat,
                    inspect_pref=inspect_pref,
                    consec_move_pref=consec_move_pref,
                )
                if seg_total > limit:
                    continue

                # deadline hard constraint
                if mandatory_enabled and min_deadline_in_interval is not None:
                    md = min_deadline_in_interval[i][j - 1]
                    if md < INF:
                        # interval 안에 required가 존재. 그 required들은 이 day에 배정됨.
                        if int(day) > int(md):
                            continue

                c = dp_cost[day - 1][i] + seg_total
                if c < best_c:
                    best_c = c
                    best_i = i

            if best_i is not None:
                dp_cost[day][j] = best_c
                dp_prev[day][j] = best_i

    # 어떤 prefix까지 스케줄링할지 선택
    # - mandatory_enabled: required가 모두 포함되도록 최소 prefix 길이 이상이어야 함
    #   required가 포함되는 최소 prefix = max position of required in route (1-based position -> prefix length)
    min_prefix = 0
    if mandatory_enabled:
        pos_map = {int(route_nodes[p]): p + 1 for p in range(m)}  # node -> prefix length position
        min_prefix = max(pos_map[int(x)] for x in required_set) if required_set else 0

    best_choice = None  # (scheduled_prefix_len, used_days, cost)
    for day in range(1, max_days + 1):
        for j in range(min_prefix, m + 1):
            if dp_cost[day][j] >= INF:
                continue
            cand = (j, day, dp_cost[day][j])
            # 최대 방문(j 최대) 우선, 그 다음 used_days 최소, 그 다음 cost 최소
            if best_choice is None:
                best_choice = cand
            else:
                if cand[0] > best_choice[0]:
                    best_choice = cand
                elif cand[0] == best_choice[0] and cand[1] < best_choice[1]:
                    best_choice = cand
                elif cand[0] == best_choice[0] and cand[1] == best_choice[1] and cand[2] < best_choice[2]:
                    best_choice = cand

    if best_choice is None:
        # 아무것도 배정 불가
        # mandatory가 있으면 infeasible
        return [], route_nodes[:], {
            "mode": "dp_split_mandatory",
            "mandatory_feasible": (not mandatory_enabled),
            "reason": "no_feasible_segment",
            "min_required_prefix": int(min_prefix),
        }

    sched_len, used_days, best_cost = best_choice

    # backtrack
    days_rev: List[List[int]] = []
    cur_j = int(sched_len)
    cur_day = int(used_days)

    while cur_day > 0 and cur_j > 0:
        prev_i = dp_prev[cur_day][cur_j]
        if prev_i is None:
            break
        i = int(prev_i)
        seg_nodes = route_nodes[i:cur_j]
        days_rev.append(seg_nodes)
        cur_j = i
        cur_day -= 1

    days = list(reversed(days_rev))

    scheduled_nodes = []
    for d in days:
        scheduled_nodes.extend(d)

    scheduled_set = set(int(x) for x in scheduled_nodes)
    unscheduled = [int(x) for x in route_nodes if int(x) not in scheduled_set]

    # mandatory feasibility check (hard)
    mandatory_feasible = True
    missing_required = []
    if mandatory_enabled:
        for idx in sorted(required_set):
            if int(idx) not in scheduled_set:
                mandatory_feasible = False
                missing_required.append(int(idx))

    # deadline violations check (hard, should be 0 if DP applied)
    # compute assigned day
    assigned_day: Dict[int, int] = {}
    for di, dnodes in enumerate(days, start=1):
        for idx in dnodes:
            assigned_day[int(idx)] = int(di)

    deadline_viol = []
    if mandatory_enabled and deadline_map:
        for idx, dd in deadline_map.items():
            if int(idx) not in assigned_day:
                continue
            if int(assigned_day[int(idx)]) > int(dd):
                deadline_viol.append({"index": int(idx), "assigned_day": int(assigned_day[int(idx)]), "deadline_day": int(dd)})
                mandatory_feasible = False

    meta = {
        "mode": "dp_split_mandatory",
        "mandatory_enabled": bool(mandatory_enabled),
        "mandatory_feasible": bool(mandatory_feasible),
        "required_count": int(len(required_set)),
        "missing_required_indices": missing_required,
        "deadline_violations": deadline_viol,
        "scheduled_count": int(len(scheduled_nodes)),
        "unscheduled_count": int(len(unscheduled)),
        "used_days": int(len(days)),
        "scheduled_prefix_len": int(sched_len),
        "dp_cost": int(best_cost) if best_cost < INF else None,
        "min_required_prefix": int(min_prefix),
    }
    return days, unscheduled, meta


# =========================================================
# Public APIs (기존 import와 호환 유지)
# =========================================================
def dp_split_days_no_return_varlimits(
    *,
    global_route: List[int],
    inspect_min: List[int],
    time_mat: List[List[int]],
    day_limits_total: List[int],
    start_idx: int,
    max_days: int,
    fallback_total_limit: int,
    # ✅ NEW (optional)
    mandatory_by_index: Optional[Dict[int, Dict[str, Any]]] = None,
) -> Tuple[List[List[int]], List[int], Dict[str, Any]]:
    """
    기존 함수 (no final return 고려 split) - 이제 mandatory 하드 제약을 선택적으로 적용
    """
    # 1) full route로 mandatory 적용 DP
    days, uns, meta = _dp_split_route_with_mandatory(
        global_route=global_route,
        inspect_min=inspect_min,
        time_mat=time_mat,
        day_limits_total=day_limits_total,
        start_idx=start_idx,
        max_days=max_days,
        fallback_total_limit=fallback_total_limit,
        mandatory_by_index=mandatory_by_index,
    )

    if meta.get("mandatory_enabled") and not meta.get("mandatory_feasible"):
        # 2) 필수만으로라도 맞춰보는 fallback (옵션 전부 unscheduled)
        req_only = _filter_route_required_only(global_route, mandatory_by_index)
        days2, uns2, meta2 = _dp_split_route_with_mandatory(
            global_route=req_only,
            inspect_min=inspect_min,
            time_mat=time_mat,
            day_limits_total=day_limits_total,
            start_idx=start_idx,
            max_days=max_days,
            fallback_total_limit=fallback_total_limit,
            mandatory_by_index=mandatory_by_index,
        )
        # unscheduled는 "원래 route에서 배정되지 않은 것"으로 재구성
        scheduled2 = set()
        for d in days2:
            for x in d:
                scheduled2.add(int(x))
        uns_full = [int(x) for x in (global_route or []) if int(x) not in scheduled2]

        meta2 = dict(meta2 or {})
        meta2["fallback_used"] = "required_only_route"
        return days2, uns_full, meta2

    return days, uns, meta


def dp_split_days_with_final_return_varlimits(
    *,
    global_route: List[int],
    inspect_min: List[int],
    time_mat: List[List[int]],
    day_limits_total: List[int],
    start_idx: int,
    max_days: int,
    fallback_total_limit: int,
    allow_next_day_for_return: bool = True,
    # ✅ NEW (optional)
    mandatory_by_index: Optional[Dict[int, Dict[str, Any]]] = None,
) -> Tuple[List[List[int]], List[int], Dict[str, Any]]:
    """
    기존 함수 (final return을 고려한 split) - 여기서는 "split 자체"는 동일하게 수행.
    실제 final return feasibility는 main_program의 simulate_days_with_final_return_hard가 판정.
    """
    days, uns, meta = dp_split_days_no_return_varlimits(
        global_route=global_route,
        inspect_min=inspect_min,
        time_mat=time_mat,
        day_limits_total=day_limits_total,
        start_idx=start_idx,
        max_days=max_days,
        fallback_total_limit=fallback_total_limit,
        mandatory_by_index=mandatory_by_index,
    )

    meta = dict(meta or {})
    meta["allow_next_day_for_return"] = bool(allow_next_day_for_return)
    meta["note"] = "Final return feasibility is checked by simulate_days_with_final_return_hard()."
    return days, uns, meta
