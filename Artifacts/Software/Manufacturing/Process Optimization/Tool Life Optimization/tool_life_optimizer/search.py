"""Deterministic multistart hill climbing; REQ-TOOL-LIFE-001 R06/R08.

Search calls the pure business evaluator. Integer grid indices avoid accumulated
step drift. Finite-batch tool changes create discontinuities, so the result is
the best feasible point found, without a global-optimum guarantee.
"""

from dataclasses import dataclass
from bisect import bisect_left
import math

from .engine import Evaluation, Scenario, evaluate, validate_scenario


MAX_GRID_SIZE = 20001
ALGORITHM = "Deterministic multistart hill climbing"


@dataclass(frozen=True)
class OptimizationResult:
    scenario: Scenario
    baseline: Evaluation
    best: Evaluation | None
    evaluations: tuple[Evaluation, ...]
    trace: tuple[dict, ...]
    grid_size: int
    message: str
    algorithm: str = ALGORITHM


def speed_grid(s: Scenario) -> tuple[float, ...]:
    """Ordered inclusive grid; the upper endpoint may have a shorter last step."""
    validate_scenario(s)
    span = s.speed_max - s.speed_min
    ratio = span / s.speed_resolution
    if not math.isfinite(ratio) or ratio > MAX_GRID_SIZE - 1:
        raise ValueError(f"Speed grid must contain at most {MAX_GRID_SIZE:,} speeds; increase resolution")
    count = math.floor(ratio)
    values = [s.speed_min + i * s.speed_resolution for i in range(count + 1)]
    # Numerical arithmetic can place an otherwise exact endpoint a few ulps off.
    if count > 0 and abs(values[-1] - s.speed_max) <= 8 * math.ulp(s.speed_max):
        values[-1] = s.speed_max
    elif values[-1] < s.speed_max:
        values.append(s.speed_max)
    else:
        values[-1] = s.speed_max
    if len(values) > MAX_GRID_SIZE:
        raise ValueError(f"Speed grid must contain at most {MAX_GRID_SIZE:,} speeds; increase resolution")
    if any(b <= a for a, b in zip(values, values[1:])):
        raise ValueError("Speed resolution is too small for distinct finite grid points")
    return tuple(values)


def _rank(e: Evaluation) -> tuple:
    return (0, e.unit_cost) if e.feasible else (1, e.violation_score, e.unit_cost)


def optimize(s: Scenario) -> OptimizationResult:
    """Bounded deterministic ascent in feasibility and descent in unit cost.

    Every visited point is retained, including the unrounded baseline. Feasible
    points outrank every infeasible point. Equal objectives do not cause moves.
    A full feasibility scan is used only if hill-climbing finds no feasible point.
    That scan stops at the first feasible point, then resumes hill climbing; it
    does not choose the cheapest point by exhaustive enumeration.
    """
    grid = speed_grid(s)
    baseline = evaluate(s, s.baseline_speed)
    cache: dict[float, Evaluation] = {baseline.speed_m_min: baseline}
    trace: list[dict] = []
    best = baseline if baseline.feasible else None

    def at(index: int) -> Evaluation:
        nonlocal best
        speed = grid[index]
        if speed not in cache:
            cache[speed] = evaluate(s, speed)
        result = cache[speed]
        if result.feasible and (best is None or
                               (result.unit_cost, result.speed_m_min) < (best.unit_cost, best.speed_m_min)):
            best = result
        return result

    def record(event: str, restart: int, index: int, step: int) -> None:
        e = at(index)
        trace.append({"event": event, "restart": restart, "index": index,
                      "step": step, "speed_m_min": e.speed_m_min,
                      "feasible": e.feasible, "unit_cost": e.unit_cost,
                      "violation_score": e.violation_score})

    def climb(start: int, restart: int) -> None:
        current = start
        record("start", restart, current, 0)
        step = 1 << max(0, (len(grid) - 1).bit_length() - 1)
        while step >= 1:
            while True:
                neighbor_indices = sorted({max(0, current - step), min(len(grid) - 1, current + step)})
                candidate = min(neighbor_indices, key=lambda i: (_rank(at(i)), i))
                if _rank(at(candidate)) >= _rank(at(current)):
                    break
                current = candidate
                record("move", restart, current, step)
            record("refine", restart, current, step)
            step //= 2
        record("finish", restart, current, 0)

    insertion = bisect_left(grid, s.baseline_speed)
    nearest_options = {min(insertion, len(grid) - 1), max(0, insertion - 1)}
    nearest = min(nearest_options, key=lambda i: (abs(grid[i] - s.baseline_speed), i))
    count = min(s.starts, len(grid))
    if count == 1:
        seeds = {len(grid) // 2}
    else:
        denominator = count - 1
        seeds = {(i * (len(grid) - 1) + denominator // 2) // denominator for i in range(count)}
    seeds.update((0, len(grid) - 1, nearest))
    for restart, start in enumerate(sorted(seeds)):
        climb(start, restart)

    fallback = False
    if best is None:
        fallback = True
        for index in range(len(grid)):
            record("feasibility_probe", len(seeds), index, 0)
            if at(index).feasible:
                climb(index, len(seeds))
                break
    if best is None:
        message = "No feasible speed exists on the configured grid; all grid points were checked for feasibility."
    else:
        message = "Best feasible point found by deterministic multistart hill climbing; a global minimum is not guaranteed."
        if fallback:
            message += " A feasibility-only scan found a starting point before hill climbing resumed."
    return OptimizationResult(s, baseline, best, tuple(cache.values()), tuple(trace), len(grid), message)
