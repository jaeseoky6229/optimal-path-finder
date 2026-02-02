from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Tuple

from optimize.dp_split import dp_split_days_with_final_return_varlimits


INF = 10**18


def _simulate_days_with_final_return_hard(
    *,
    start_idx: int,
    days: List[List[int]],
    time_mat: List[List[int]],
    inspect_min: List[int],
    day_limits_total: List[int],
    max_days: int,
    allow_next_day_for_return: bool = True,
) -> Dict[str, Any]:
    """
    main_program.py의 simulate_days_with_final_return_hard와 동일한 정책(핵심만 복제):
    - no daily return
    - final return is mandatory, can spill to next day if fits
    - feasibility check based on time_mat durations + inspect_min
    """
    limits = [int(x) for x in (day_limits_total or [])][: int(max_days)]
    if len(limits) < int(max_days):
        last = limits[-1] if limits else 480
        while len(limits) < int(max_days):
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

        chain = [cur_pos] + (dnodes or [])
        for i in range(len(chain) - 1):
            dm += int(time_mat[int(chain[i])][int(chain[i + 1])])

        for x in (dnodes or []):
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
                if next_i < int(max_days) and return_move <= int(limits[next_i]):
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


def _ordered_crossover(p1: List[int], p2: List[int], rng: random.Random) -> List[int]:
    n = len(p1)
    if n <= 2:
        return p1[:]
    a = rng.randrange(0, n)
    b = rng.randrange(0, n)
    if a > b:
        a, b = b, a
    hole = set(p1[a:b+1])
    child = [None] * n
    child[a:b+1] = p1[a:b+1]
    fill = [x for x in p2 if x not in hole]
    k = 0
    for i in range(n):
        if child[i] is None:
            child[i] = fill[k]
            k += 1
    return [int(x) for x in child]  # type: ignore


def _mutate_swap(route: List[int], rng: random.Random, rate: float) -> List[int]:
    r = route[:]
    if len(r) <= 2:
        return r
    if rng.random() < rate:
        i = rng.randrange(0, len(r))
        j = rng.randrange(0, len(r))
        r[i], r[j] = r[j], r[i]
    return r


def _tournament(pop: List[Tuple[List[int], Tuple]], rng: random.Random, k: int = 3) -> List[int]:
    best = None
    for _ in range(max(1, k)):
        cand = rng.choice(pop)
        if best is None or cand[1] < best[1]:
            best = cand
    return best[0][:]  # type: ignore


def solve_ga_multiday_no_return(
    *,
    start_idx: int,
    nodes: List[int],
    time_mat: List[List[int]],
    inspect_min: List[int],
    day_limits_total: List[int],
    max_days: int,
    seed: int = 42,
    # ---- GA params (필요 시 main에서 payload로 받을 수 있음)
    pop_size: int = 80,
    generations: int = 160,
    elite: int = 6,
    cx_rate: float = 0.85,
    mut_rate: float = 0.20,
    tournament_k: int = 3,
    # ---- 정책
    allow_next_day_for_return: bool = True,
    # ✅ NEW: mandatory hard constraints (points index 기준)
    mandatory_by_index: Optional[Dict[int, Dict[str, Any]]] = None,
) -> Tuple[List[int], Dict[str, Any]]:
    """
    혼합 관할청 케이스용 GA:
    - GA는 "global_route(순서)"를 찾고,
    - split은 DP(dp_split.py)로 처리 (필수/마감 hard constraint 포함)
    - final return feasibility도 같이 만족해야 feasible로 인정
    """
    rng = random.Random(int(seed))

    nodes = [int(x) for x in (nodes or [])]
    n = len(nodes)

    if n == 0:
        sim = _simulate_days_with_final_return_hard(
            start_idx=int(start_idx),
            days=[],
            time_mat=time_mat,
            inspect_min=inspect_min,
            day_limits_total=day_limits_total,
            max_days=int(max_days),
            allow_next_day_for_return=bool(allow_next_day_for_return),
        )
        return [], {"sim": sim, "note": "empty nodes"}

    # ---- 초기 population 생성
    def _make_one() -> List[int]:
        r = nodes[:]
        rng.shuffle(r)
        return r

    # ---- fitness 평가
    # fitness 튜플: 작을수록 좋음
    # 0) infeasible_flag (0 feasible, 1 infeasible)
    # 1) -scheduled_count (많이 배정될수록 좋음)
    # 2) used_days (적을수록 좋음)
    # 3) last_day_total (적을수록 좋음)
    # 4) total_move (적을수록 좋음)
    def _evaluate(route: List[int]) -> Tuple[Tuple, Dict[str, Any]]:
        days_try, uns_try, dp_meta = dp_split_days_with_final_return_varlimits(
            global_route=route,
            inspect_min=inspect_min,
            time_mat=time_mat,
            day_limits_total=day_limits_total,
            start_idx=int(start_idx),
            max_days=int(max_days),
            fallback_total_limit=480,
            allow_next_day_for_return=bool(allow_next_day_for_return),
            mandatory_by_index=mandatory_by_index,
        )

        # DP 레벨에서 mandatory infeasible이면 즉시 탈락(하드 제약)
        if dp_meta and dp_meta.get("mandatory_enabled") and not dp_meta.get("mandatory_feasible"):
            fit = (1, INF, INF, INF, INF)
            sim = {"feasible": False, "days": [], "unscheduled": route[:], "final_return": {"required": True, "added": False}}
            return fit, {"dp_meta": dp_meta, "sim": sim}

        sim2 = _simulate_days_with_final_return_hard(
            start_idx=int(start_idx),
            days=days_try,
            time_mat=time_mat,
            inspect_min=inspect_min,
            day_limits_total=day_limits_total,
            max_days=int(max_days),
            allow_next_day_for_return=bool(allow_next_day_for_return),
        )

        if not bool(sim2.get("feasible", False)):
            fit = (1, INF, INF, INF, INF)
            return fit, {"dp_meta": dp_meta, "sim": sim2, "unscheduled": uns_try}

        scheduled_count = int(sum(len(d) for d in (sim2.get("days") or [])))
        used_days = int(sim2.get("used_days", 10**9))
        last_day_total = int(sim2.get("last_day_total", 10**9))
        total_move = int(sim2.get("total_move", 10**9))

        fit = (0, -scheduled_count, used_days, last_day_total, total_move)
        return fit, {"dp_meta": dp_meta, "sim": sim2, "unscheduled": uns_try}

    pop: List[Tuple[List[int], Tuple]] = []
    pop_meta: Dict[int, Dict[str, Any]] = {}

    for i in range(int(pop_size)):
        r = _make_one()
        fit, meta = _evaluate(r)
        pop.append((r, fit))
        pop_meta[i] = meta

    # best tracking
    best_route = None
    best_fit = None
    best_meta = None

    def _update_best():
        nonlocal best_route, best_fit, best_meta
        for (r, f) in pop:
            if best_fit is None or f < best_fit:
                best_fit = f
                best_route = r[:]
        # best_meta는 마지막에 best_route 재평가로 채움

    _update_best()

    # ---- GA loop
    for g in range(int(generations)):
        pop.sort(key=lambda x: x[1])
        elites = [pop[i][0][:] for i in range(min(int(elite), len(pop)))]

        next_routes: List[List[int]] = []
        next_routes.extend(elites)

        while len(next_routes) < int(pop_size):
            p1 = _tournament(pop, rng, k=int(tournament_k))
            p2 = _tournament(pop, rng, k=int(tournament_k))

            if rng.random() < float(cx_rate):
                c = _ordered_crossover(p1, p2, rng)
            else:
                c = p1[:]

            c = _mutate_swap(c, rng, rate=float(mut_rate))
            next_routes.append(c)

        # 평가
        new_pop: List[Tuple[List[int], Tuple]] = []
        for r in next_routes:
            fit, _ = _evaluate(r)
            new_pop.append((r, fit))
        pop = new_pop
        _update_best()

    if best_route is None:
        best_route = nodes[:]

    # best 재평가(meta 확보)
    best_fit, best_meta = _evaluate(best_route)
    sim = (best_meta or {}).get("sim", {}) or {}
    uns = (best_meta or {}).get("unscheduled", []) or []
    dp_meta = (best_meta or {}).get("dp_meta", {}) or {}

    # ga_meta 형식은 기존 사용처(main_program)와 최대한 호환되게 구성
    ga_meta_out = {
        "seed": int(seed),
        "pop_size": int(pop_size),
        "generations": int(generations),
        "elite": int(elite),
        "cx_rate": float(cx_rate),
        "mut_rate": float(mut_rate),
        "tournament_k": int(tournament_k),
        "best_fitness": best_fit,
        "dp_meta": dp_meta,
        "sim": {
            # main_program이 기대하는 키들에 맞춤
            "feasible": bool(sim.get("feasible", False)),
            "days": sim.get("days", []) or [],
            "unscheduled": [int(x) for x in uns],
            "final_return": sim.get("final_return", {}) or {},
            "used_days": int(sim.get("used_days", 0) or 0),
            "total_move": int(sim.get("total_move", 0) or 0),
            "total_insp": int(sim.get("total_insp", 0) or 0),
            "total": int(sim.get("total", 0) or 0),
            "last_day_total": int(sim.get("last_day_total", 0) or 0),
        },
        "mandatory": {
            "enabled": bool((dp_meta or {}).get("mandatory_enabled", False)),
            "hard_constraint": True,
            "mandatory_feasible": bool((dp_meta or {}).get("mandatory_feasible", True)),
            "note": "DP split enforces required/deadline. GA searches only ordering.",
        }
    }

    return best_route, ga_meta_out
