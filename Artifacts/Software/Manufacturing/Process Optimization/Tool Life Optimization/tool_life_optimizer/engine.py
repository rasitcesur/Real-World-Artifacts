"""Committed fixed-condition machining and finite-batch business semantics.

REQ-TOOL-LIFE-001 R01--R05; approved assumptions A-001--A-003.
Life is accumulated cutter-in-cut clock minutes, including interrupted milling.
It is not the sum of contact minutes over the individual teeth.  Calibration is
specific to the selected operation, tool, material and fixed cutting conditions.
"""

from dataclasses import dataclass
import math


CAPACITY_ULPS = 8


@dataclass(frozen=True)
class Scenario:
    name: str
    operation: str
    currency: str
    material_name: str
    hardness_label: str
    tool_name: str
    coolant: str
    calibration_kind: str
    calibration_source: str
    diameter_mm: float
    cut_length_mm: float
    passes: int
    feed_turn_mm_rev: float
    feed_mill_mm_tooth: float
    teeth: int
    insert_positions: int
    tool_type: str
    depth_mm: float
    width_mm: float
    specific_force_n_mm2: float
    v_ref_m_min: float
    life_ref_min: float
    taylor_exponent: float
    demand_qty: int
    setup_minutes: float
    noncut_minutes: float
    tool_change_minutes: float
    machine_rate_hour: float
    tool_cost: float
    other_cost_per_part: float
    other_batch_cost: float
    available_minutes: float | None
    rpm_min: float
    rpm_max: float
    axis_feed_max_mm_min: float
    motor_power_kw: float
    efficiency: float
    speed_min: float
    speed_max: float
    baseline_speed: float
    speed_resolution: float
    starts: int


@dataclass(frozen=True)
class Evaluation:
    speed_m_min: float
    spindle_rpm: float
    feed_mm_min: float
    cut_minutes: float
    predicted_life_minutes: float
    parts_per_tool: int
    tool_sets: int
    tool_changes: int
    batch_minutes: float
    cutting_power_kw: float
    motor_power_kw: float
    unit_cost: float
    machine_cost_per_part: float
    tooling_cost_per_part: float
    other_cost_per_part: float
    feasible: bool
    violations: tuple[str, ...]
    violation_score: float


def demo_scenario(operation: str = "turning") -> Scenario:
    """Independent synthetic examples, never supplier or measured cut data."""
    if operation not in ("turning", "milling"):
        raise ValueError("operation must be turning or milling")
    turning = operation == "turning"
    return Scenario(
        name=f"Synthetic {operation} demonstration", operation=operation,
        currency="CU", material_name="Synthetic metal example",
        hardness_label="Demonstration only; no measured hardness",
        tool_name="Synthetic turning edge" if turning else "Synthetic 4-insert cutter",
        coolant="Fixed demonstration condition", calibration_kind="demonstration",
        calibration_source="Synthetic independent example; not production cutting data",
        diameter_mm=60.0 if turning else 40.0,
        cut_length_mm=100.0 if turning else 250.0, passes=1,
        feed_turn_mm_rev=0.20, feed_mill_mm_tooth=0.08,
        teeth=4, insert_positions=4, tool_type="indexable",
        depth_mm=2.0, width_mm=20.0, specific_force_n_mm2=1800.0,
        v_ref_m_min=180.0 if turning else 140.0,
        life_ref_min=30.0 if turning else 22.0,
        taylor_exponent=0.25 if turning else 0.30,
        demand_qty=200, setup_minutes=20.0, noncut_minutes=0.50,
        tool_change_minutes=3.0 if turning else 5.0,
        machine_rate_hour=60.0, tool_cost=7.0 if turning else 9.0,
        other_cost_per_part=2.0, other_batch_cost=0.0,
        available_minutes=300.0, rpm_min=100.0, rpm_max=6000.0,
        axis_feed_max_mm_min=5000.0, motor_power_kw=15.0, efficiency=0.85,
        speed_min=60.0 if turning else 50.0,
        speed_max=300.0 if turning else 250.0,
        baseline_speed=180.0 if turning else 140.0,
        speed_resolution=1.0, starts=7,
    )


def _number(value: object, field: str, *, positive: bool) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite number")
    try:
        finite = math.isfinite(value)
    except (OverflowError, TypeError):
        finite = False
    if not finite or (value <= 0 if positive else value < 0):
        qualifier = "positive" if positive else "nonnegative"
        raise ValueError(f"{field} must be finite and {qualifier}")


def validate_scenario(s: Scenario) -> None:
    """Reject invalid model inputs; inactive feed/width may be zero.

    A valid scenario can still have no feasible operating point. Limits therefore
    are not silently expanded to accommodate the baseline or demand.
    """
    if not isinstance(s, Scenario):
        raise ValueError("scenario must be a Scenario")
    for field in ("name", "currency", "material_name", "hardness_label", "tool_name", "coolant"):
        value = getattr(s, field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be nonblank text")
    if s.operation not in ("turning", "milling"):
        raise ValueError("operation must be turning or milling")
    if s.tool_type not in ("indexable", "solid"):
        raise ValueError("tool_type must be indexable or solid")
    if s.calibration_kind not in ("demonstration", "measured", "supplier"):
        raise ValueError("calibration_kind must be demonstration, measured or supplier")
    if not isinstance(s.calibration_source, str):
        raise ValueError("calibration_source must be text")
    if s.calibration_kind != "demonstration" and not s.calibration_source.strip():
        raise ValueError("Measured/supplier calibration requires a source and matching-condition note")
    for field in ("passes", "teeth", "insert_positions", "demand_qty", "starts"):
        value = getattr(s, field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{field} must be a positive integer")
    for field in ("diameter_mm", "cut_length_mm", "depth_mm", "specific_force_n_mm2",
                  "v_ref_m_min", "life_ref_min", "taylor_exponent", "rpm_max",
                  "axis_feed_max_mm_min", "motor_power_kw", "efficiency",
                  "speed_min", "speed_max", "baseline_speed", "speed_resolution"):
        _number(getattr(s, field), field, positive=True)
    for field in ("feed_turn_mm_rev", "feed_mill_mm_tooth", "width_mm", "setup_minutes",
                  "noncut_minutes", "tool_change_minutes", "machine_rate_hour", "tool_cost",
                  "other_cost_per_part", "other_batch_cost", "rpm_min"):
        _number(getattr(s, field), field, positive=False)
    _number(s.feed_turn_mm_rev if s.operation == "turning" else s.feed_mill_mm_tooth,
            "active feed", positive=True)
    if s.operation == "milling":
        _number(s.width_mm, "width_mm", positive=True)
        if s.width_mm > s.diameter_mm:
            raise ValueError("Milling radial engagement width must not exceed the effective cutter diameter")
    if s.available_minutes is not None:
        _number(s.available_minutes, "available_minutes", positive=True)
    if s.efficiency > 1:
        raise ValueError("efficiency must be greater than 0 and at most 1")
    if s.rpm_min > s.rpm_max:
        raise ValueError("rpm_min must not exceed rpm_max")
    if s.speed_min > s.speed_max:
        raise ValueError("speed_min must not exceed speed_max")
    if not s.speed_min <= s.baseline_speed <= s.speed_max:
        raise ValueError("baseline_speed must lie within the configured speed range")


def _numerical_failure(speed: float, reason: str) -> Evaluation:
    return Evaluation(
        speed, math.inf, math.inf, math.inf, 0.0, 0, 0, 0, math.inf,
        math.inf, math.inf, math.inf, math.inf, math.inf, math.inf,
        False, (reason,), math.inf,
    )


def _parts_capacity(life: float, cut: float) -> int:
    """Snap only within eight binary64 ulps of a positive integer boundary.

    This absorbs arithmetic roundoff in mathematically exact T / t_cut values.
    It is not a percentage wear allowance. The same clock-time basis is used in
    both modes; neither effective teeth nor insert count scales life exposure.
    """
    quotient = life / cut
    if not math.isfinite(quotient):
        raise OverflowError("Tool capacity exceeds the supported numerical range")
    nearest = round(quotient)
    if nearest >= 1 and abs(quotient - nearest) <= CAPACITY_ULPS * math.ulp(quotient):
        quotient = nearest
    return math.floor(quotient)


def evaluate(s: Scenario, speed: float) -> Evaluation:
    """Evaluate one candidate without UI, persistence or search dependencies."""
    validate_scenario(s)
    if isinstance(speed, bool) or not isinstance(speed, (int, float)):
        return _numerical_failure(math.nan, "Cutting speed must be a finite positive number")
    try:
        v = float(speed)
    except (OverflowError, ValueError):
        return _numerical_failure(math.nan, "Cutting speed must be a finite positive number")
    if not math.isfinite(v) or v <= 0:
        return _numerical_failure(v, "Cutting speed must be a finite positive number")
    try:
        rpm = 1000.0 * v / (math.pi * s.diameter_mm)
        feed = (s.feed_turn_mm_rev * rpm if s.operation == "turning"
                else s.feed_mill_mm_tooth * rpm * s.teeth)
        cut = s.passes * s.cut_length_mm / feed
        life = s.life_ref_min * math.exp(
            (math.log(s.v_ref_m_min) - math.log(v)) / s.taylor_exponent)
        power = (v * s.depth_mm * s.feed_turn_mm_rev * s.specific_force_n_mm2 / 60000.0
                 if s.operation == "turning" else
                 s.depth_mm * s.width_mm * feed * s.specific_force_n_mm2 / 60000000.0)
        motor_power = power / s.efficiency
        if not all(math.isfinite(x) and x > 0 for x in (rpm, feed, cut, life, power, motor_power)):
            return _numerical_failure(v, "Machining calculation is outside the finite numerical range")
        capacity = _parts_capacity(life, cut)
        sets = (s.demand_qty + capacity - 1) // capacity if capacity >= 1 else 0
        changes = max(0, sets - 1)
        batch = s.setup_minutes + s.demand_qty * (s.noncut_minutes + cut) + changes * s.tool_change_minutes
        set_cost = (s.tool_cost * s.insert_positions
                    if s.operation == "milling" and s.tool_type == "indexable" else s.tool_cost)
        machine_cost = (s.machine_rate_hour / 60.0) * batch / s.demand_qty
        tooling_cost = sets * set_cost / s.demand_qty if capacity >= 1 else math.inf
        other_cost = s.other_cost_per_part + s.other_batch_cost / s.demand_qty
        unit_cost = machine_cost + tooling_cost + other_cost
        if not all(math.isfinite(x) for x in (batch, set_cost, machine_cost, other_cost)):
            return _numerical_failure(v, "Batch calculation is outside the finite numerical range")
        if capacity >= 1 and not math.isfinite(unit_cost):
            return _numerical_failure(v, "Cost calculation is outside the finite numerical range")
    except (OverflowError, ZeroDivisionError, ValueError):
        return _numerical_failure(v, "Machining calculation is outside the finite numerical range")
    violations: list[str] = []
    score = 0.0

    def upper(actual: float, limit: float, label: str) -> None:
        nonlocal score
        if actual > limit:
            violations.append(label)
            score += (actual - limit) / limit

    def lower(actual: float, limit: float, label: str) -> None:
        nonlocal score
        if actual < limit:
            violations.append(label)
            score += (limit - actual) / limit

    lower(v, s.speed_min, "Below minimum cutting speed")
    upper(v, s.speed_max, "Above maximum cutting speed")
    if s.rpm_min > 0:
        lower(rpm, s.rpm_min, "Below minimum spindle RPM")
    upper(rpm, s.rpm_max, "Above maximum spindle RPM")
    upper(feed, s.axis_feed_max_mm_min, "Axis feed limit exceeded")
    upper(motor_power, s.motor_power_kw, "Motor power limit exceeded")
    if capacity < 1:
        violations.append("Tool life cannot complete one part")
        score += max(0.0, (cut - life) / cut)
    if s.available_minutes is not None:
        upper(batch, s.available_minutes, "Available batch minutes exceeded")
    return Evaluation(
        v, rpm, feed, cut, life, capacity, sets, changes, batch, power,
        motor_power, unit_cost, machine_cost, tooling_cost, other_cost,
        not violations, tuple(violations), score,
    )
