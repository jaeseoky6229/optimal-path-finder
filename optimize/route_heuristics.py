# optimize/route_heuristics.py
import random
from typing import List

def chain_cost_from_start(start_idx: int, route: List[int], time_mat: List[List[int]], *, return_to_depot: bool = False) -> int:
    if not route:
        return 0
    cost = int(time_mat[start_idx][route[0]])
    for i in range(len(route) - 1):
        cost += int(time_mat[route[i]][route[i + 1]])
    if return_to_depot:
        cost += int(time_mat[route[-1]][start_idx])
    return int(cost)

def nearest_neighbor_route_from_start(start_idx: int, nodes: List[int], time_mat: List[List[int]]) -> List[int]:
    if not nodes:
        return []
    unvisited = set(int(x) for x in nodes)
    cur = min(unvisited, key=lambda j: time_mat[start_idx][j])
    route = [cur]
    unvisited.remove(cur)
    while unvisited:
        nxt = min(unvisited, key=lambda j: time_mat[cur][j])
        route.append(nxt)
        unvisited.remove(nxt)
        cur = nxt
    return route

def randomized_nn_route_from_start(start_idx: int, nodes: List[int], time_mat: List[List[int]], *, rng: random.Random, k: int = 3) -> List[int]:
    if not nodes:
        return []
    unvisited = set(int(x) for x in nodes)
    cand = sorted(unvisited, key=lambda j: time_mat[start_idx][j])
    pick = cand[0] if k <= 1 else rng.choice(cand[: min(k, len(cand))])
    route = [pick]
    unvisited.remove(pick)
    cur = pick
    while unvisited:
        cand = sorted(unvisited, key=lambda j: time_mat[cur][j])
        pick = cand[0] if k <= 1 else rng.choice(cand[: min(k, len(cand))])
        route.append(pick)
        unvisited.remove(pick)
        cur = pick
    return route

def make_candidate_routes_multistart(start_idx: int, nodes: List[int], time_mat: List[List[int]], *, iters: int = 50, rnn_k: int = 3, seed: int = 42) -> List[List[int]]:
    rng = random.Random(seed)
    routes: List[List[int]] = [nearest_neighbor_route_from_start(start_idx, nodes, time_mat)]
    for _ in range(max(0, iters - 1)):
        routes.append(randomized_nn_route_from_start(start_idx, nodes, time_mat, rng=rng, k=rnn_k))
    return routes

def two_opt_chain_from_start(start_idx: int, route: List[int], time_mat: List[List[int]]) -> List[int]:
    if len(route) < 4:
        return route[:]

    def cost(r: List[int]) -> int:
        return chain_cost_from_start(start_idx, r, time_mat, return_to_depot=False)

    best = route[:]
    improved = True
    while improved:
        improved = False
        best_cost = cost(best)
        n = len(best)
        for i in range(0, n - 2):
            for k in range(i + 1, n - 1):
                new_route = best[:i] + best[i:k + 1][::-1] + best[k + 1:]
                new_cost = cost(new_route)
                if new_cost < best_cost:
                    best, best_cost = new_route, new_cost
                    improved = True
                    break
            if improved:
                break
    return best
