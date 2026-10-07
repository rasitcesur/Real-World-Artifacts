"""REQ-TOOL-LIFE-001 model and search acceptance tests.

Golden numbers come from written hand arithmetic in golden_vectors.json.
The exhaustive oracle below has its own small, specified turning model and
does not call the production evaluator. These tests validate the declared
fixed-condition model, not measured machining performance.
"""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
import inspect
import json
import math
from pathlib import Path
import unittest

from tool_life_optimizer import engine
from tool_life_optimizer.engine import Scenario, demo_scenario, evaluate, validate_scenario
from tool_life_optimizer.search import optimize, speed_grid


GOLDEN = json.loads(Path(__file__).with_name("golden_vectors.json").read_text(encoding="utf-8"))


def fixture(operation: str = "turning", **changes) -> Scenario:
    """Construct an explicit independent scenario, without production demos."""
    values = dict(GOLDEN["common_scenario"])
    values["operation"] = operation
    if operation == "milling":
        values.update(GOLDEN["vectors"][1]["scenario_overrides"])
    values.update(changes)
    return Scenario(**values)


def independent_turning_cost(s: Scenario, speed: float) -> tuple[float, bool]:
    """R06 exhaustive oracle with separate scalar arithmetic and no tolerance.

    Tests use capacities far from rounding boundaries. Geometry and Taylor
    constants are taken as inputs, while this function independently derives
    complete-part capacity, full tooling allocation, time and total cost.
    """
    revolutions_per_minute = speed * 1000.0 / (math.pi * s.diameter_mm)
    linear_feed = revolutions_per_minute * s.feed_turn_mm_rev
    one_part_minutes = s.cut_length_mm * s.passes / linear_feed
    life = s.life_ref_min * (s.v_ref_m_min / speed) ** (1.0 / s.taylor_exponent)
    capacity = int(life // one_part_minutes)
    power = (speed * s.depth_mm * s.feed_turn_mm_rev * s.specific_force_n_mm2
             / 60000.0 / s.efficiency)
    if capacity < 1:
        return math.inf, False
    sets = (s.demand_qty + capacity - 1) // capacity
    duration = (s.setup_minutes + s.demand_qty * (one_part_minutes + s.noncut_minutes)
                + (sets - 1) * s.tool_change_minutes)
    feasible = (s.speed_min <= speed <= s.speed_max
                and s.rpm_min <= revolutions_per_minute <= s.rpm_max
                and linear_feed <= s.axis_feed_max_mm_min
                and power <= s.motor_power_kw
                and (s.available_minutes is None or duration <= s.available_minutes))
    cost = (duration * s.machine_rate_hour / 60.0 + sets * s.tool_cost
            + s.demand_qty * s.other_cost_per_part + s.other_batch_cost) / s.demand_qty
    return cost, feasible


class GoldenArithmeticTests(unittest.TestCase):
    """R01-R04: fixed, independently derived arithmetic and accounting."""

    def test_all_frozen_hand_calculated_vectors(self):
        for vector in GOLDEN["vectors"]:
            with self.subTest(vector=vector["name"]):
                scenario = fixture(**vector["scenario_overrides"])
                result = evaluate(scenario, vector["speed_m_min"])
                for field, expected in vector["expected"].items():
                    actual = getattr(result, field)
                    if isinstance(expected, bool) or isinstance(expected, int):
                        self.assertEqual(actual, expected, field)
                    else:
                        self.assertAlmostEqual(actual, expected, places=11, msg=field)
                self.assertEqual(result.violations, ())
                self.assertAlmostEqual(
                    result.unit_cost,
                    result.machine_cost_per_part + result.tooling_cost_per_part
                    + result.other_cost_per_part, places=12)

    def test_one_part_charges_fresh_edge_without_change(self):
        s = fixture(demand_qty=1)
        result = evaluate(s, s.v_ref_m_min)
        self.assertEqual((result.tool_sets, result.tool_changes), (1, 0))
        self.assertAlmostEqual(result.batch_minutes, 11.5)
        self.assertAlmostEqual(result.unit_cost, 31.5)

    def test_exact_complete_part_capacity_has_no_spurious_change(self):
        s = fixture(demand_qty=10)
        result = evaluate(s, s.v_ref_m_min)
        self.assertEqual((result.parts_per_tool, result.tool_sets, result.tool_changes), (10, 1, 0))
        self.assertAlmostEqual(result.batch_minutes, 25.0)
        self.assertAlmostEqual(result.unit_cost, 6.3)

    def test_first_part_beyond_capacity_charges_entire_next_edge(self):
        s = fixture(demand_qty=11)
        result = evaluate(s, s.v_ref_m_min)
        self.assertEqual((result.parts_per_tool, result.tool_sets, result.tool_changes), (10, 2, 1))
        self.assertAlmostEqual(result.batch_minutes, 30.5)
        self.assertAlmostEqual(result.unit_cost, 76.5 / 11)

    def test_between_part_changes_do_not_use_pooled_fractional_life(self):
        # Each part consumes 6 minutes while each tool lasts 10: one part per
        # tool. Pooled 18/10 would allocate only 2 tools, which cannot finish
        # three parts under the approved between-part replacement rule.
        s = fixture(cut_length_mm=600.0, demand_qty=3)
        result = evaluate(s, s.v_ref_m_min)
        self.assertEqual((result.parts_per_tool, result.tool_sets, result.tool_changes), (1, 3, 2))
        self.assertAlmostEqual(result.batch_minutes, 37.5)
        self.assertAlmostEqual(result.unit_cost, 24.5)

    def test_capacity_tolerance_is_limited_to_eight_ulps(self):
        # Choose length from independent spindle/feed arithmetic so one part
        # consumes exactly one binary64 minute. A nominal 100mm length in the
        # pi fixture gives a one-ulp-short time and would confound this test.
        reference = fixture()
        independent_feed = 0.2 * (1000.0 * reference.v_ref_m_min / (math.pi * 100.0))
        unit = math.ulp(10.0)
        for difference, expected in [(0, 10), (8, 10), (9, 9), (1000, 9)]:
            with self.subTest(ulps_below=difference):
                s = fixture(cut_length_mm=independent_feed / 2.0,
                            life_ref_min=10.0 - difference * unit)
                result = evaluate(s, s.v_ref_m_min)
                self.assertEqual(result.cut_minutes, 1.0)
                self.assertEqual(result.parts_per_tool, expected)

    def test_milling_effective_teeth_and_physical_positions_are_distinct(self):
        s = fixture("milling")
        original = evaluate(s, s.v_ref_m_min)
        more_positions = evaluate(replace(s, insert_positions=8), s.v_ref_m_min)
        self.assertAlmostEqual(more_positions.feed_mm_min, original.feed_mm_min)
        self.assertAlmostEqual(more_positions.cut_minutes, original.cut_minutes)
        self.assertAlmostEqual(more_positions.tooling_cost_per_part, 3 * 8 * 8 / 25)

    def test_solid_milling_cost_is_independent_of_insert_positions(self):
        s = fixture("milling", tool_type="solid", tool_cost=80.0)
        original = evaluate(s, s.v_ref_m_min)
        changed = evaluate(replace(s, insert_positions=8), s.v_ref_m_min)
        self.assertEqual(original, changed)

    def test_fixed_other_costs_do_not_change_time_or_life(self):
        s = fixture(other_cost_per_part=0.0, other_batch_cost=0.0)
        original = evaluate(s, s.v_ref_m_min)
        changed = evaluate(replace(s, other_cost_per_part=7.0, other_batch_cost=50.0), s.v_ref_m_min)
        self.assertEqual(changed.batch_minutes, original.batch_minutes)
        self.assertEqual(changed.predicted_life_minutes, original.predicted_life_minutes)
        self.assertAlmostEqual(changed.unit_cost - original.unit_cost, 7.0 + 50.0 / 25)


class CalibrationAndConstraintTests(unittest.TestCase):
    """R02, R05: physical-model identity and hard feasibility limits."""

    def test_taylor_reference_identity_and_monotonic_life(self):
        for operation in ("turning", "milling"):
            with self.subTest(operation=operation):
                s = fixture(operation)
                reference = evaluate(s, s.v_ref_m_min)
                slower = evaluate(s, s.v_ref_m_min / 2.0)
                faster = evaluate(s, s.v_ref_m_min * 2.0)
                self.assertEqual(reference.predicted_life_minutes, 10.0)
                self.assertAlmostEqual(slower.predicted_life_minutes, 40.0)
                self.assertAlmostEqual(faster.predicted_life_minutes, 2.5)
                self.assertGreater(slower.predicted_life_minutes, reference.predicted_life_minutes)
                self.assertGreater(reference.predicted_life_minutes, faster.predicted_life_minutes)

    def test_turning_and_milling_profiles_are_independent(self):
        turning = fixture(life_ref_min=20.0)
        milling = fixture("milling", life_ref_min=7.0)
        self.assertEqual(evaluate(turning, turning.v_ref_m_min).predicted_life_minutes, 20.0)
        self.assertEqual(evaluate(milling, milling.v_ref_m_min).predicted_life_minutes, 7.0)

    def test_machine_and_batch_limits_each_reject_candidate(self):
        cases = {
            "minimum RPM": {"rpm_min": 1001.0},
            "maximum RPM": {"rpm_max": 999.0},
            "axis feed": {"axis_feed_max_mm_min": 199.0},
            "motor power": {"motor_power_kw": 3.9},
            "batch time": {"available_minutes": 55.49},
            "one part life": {"life_ref_min": 0.9},
        }
        for label, changes in cases.items():
            with self.subTest(limit=label):
                s = fixture(**changes)
                result = evaluate(s, s.v_ref_m_min)
                self.assertFalse(result.feasible)
                self.assertTrue(result.violations)
                self.assertGreater(result.violation_score, 0.0)

    def test_hard_limits_accept_equality(self):
        # R01 vectors separately check independent physical arithmetic. Here
        # the boundary test uses identical binary64 values for actual/limit;
        # decimal or pi rounding must not be confused with exact equality.
        reference = fixture()
        actual = evaluate(reference, reference.v_ref_m_min)
        s = replace(reference, rpm_min=actual.spindle_rpm, rpm_max=actual.spindle_rpm,
                    axis_feed_max_mm_min=actual.feed_mm_min,
                    motor_power_kw=actual.motor_power_kw,
                    available_minutes=actual.batch_minutes)
        self.assertTrue(evaluate(s, s.v_ref_m_min).feasible)

    def test_invalid_candidate_speed_returns_infeasible_result(self):
        s = fixture()
        for speed in (math.nan, math.inf, -math.inf, 0.0, -1.0, True,
                      s.speed_min / 2.0, s.speed_max + 1.0):
            with self.subTest(speed=speed):
                result = evaluate(s, speed)
                self.assertFalse(result.feasible)
                self.assertTrue(result.violations)

    def test_no_feasible_speed_reports_no_solution(self):
        s = fixture(motor_power_kw=0.000001)
        result = optimize(s)
        self.assertIsNone(result.best)
        self.assertTrue(result.evaluations)
        self.assertTrue(all(not e.feasible for e in result.evaluations))

    def test_finite_input_overflow_is_cleanly_infeasible_and_never_selected(self):
        s = fixture(specific_force_n_mm2=1e308, speed_min=100.0, speed_max=120.0,
                    baseline_speed=110.0, speed_resolution=10.0)
        result = evaluate(s, s.baseline_speed)
        self.assertFalse(result.feasible)
        self.assertTrue(result.violations)
        self.assertTrue(math.isinf(result.unit_cost))
        self.assertIsNone(optimize(s).best)


class InputValidationTests(unittest.TestCase):
    """R03, R05: invalid inputs cannot silently alter mathematical semantics."""

    def test_scenario_is_frozen(self):
        s = fixture()
        with self.assertRaises(FrozenInstanceError):
            s.demand_qty = 2

    def test_nonfinite_numeric_inputs_are_rejected(self):
        fields = ["diameter_mm", "cut_length_mm", "feed_turn_mm_rev", "feed_mill_mm_tooth",
                  "depth_mm", "width_mm", "specific_force_n_mm2", "v_ref_m_min",
                  "life_ref_min", "taylor_exponent", "setup_minutes", "noncut_minutes",
                  "tool_change_minutes", "machine_rate_hour", "tool_cost", "other_cost_per_part",
                  "other_batch_cost", "available_minutes", "rpm_min", "rpm_max",
                  "axis_feed_max_mm_min", "motor_power_kw", "efficiency", "speed_min",
                  "speed_max", "baseline_speed", "speed_resolution"]
        for field in fields:
            for invalid in (math.nan, math.inf, -math.inf):
                with self.subTest(field=field, value=invalid):
                    with self.assertRaises(ValueError):
                        validate_scenario(fixture(**{field: invalid}))

    def test_positive_quantities_reject_zero_and_negative(self):
        for field in ("diameter_mm", "cut_length_mm", "feed_turn_mm_rev",
                      "depth_mm", "specific_force_n_mm2", "v_ref_m_min",
                      "life_ref_min", "taylor_exponent", "rpm_max", "axis_feed_max_mm_min",
                      "motor_power_kw", "efficiency", "speed_min", "speed_resolution"):
            for value in (0, -1):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValueError):
                        validate_scenario(fixture(**{field: value}))
        for field in ("feed_mill_mm_tooth", "width_mm"):
            for value in (0, -1):
                with self.subTest(operation="milling", field=field, value=value):
                    with self.assertRaises(ValueError):
                        validate_scenario(fixture("milling", **{field: value}))

    def test_inactive_feed_and_width_may_be_zero(self):
        validate_scenario(fixture(feed_mill_mm_tooth=0.0, width_mm=0.0))
        validate_scenario(fixture("milling", feed_turn_mm_rev=0.0))

    def test_milling_width_cannot_exceed_effective_cutter_diameter(self):
        validate_scenario(fixture("milling", width_mm=20.0))
        with self.assertRaises(ValueError):
            validate_scenario(fixture("milling", width_mm=20.01))
        # Turning width is inactive and must not impose a milling constraint.
        validate_scenario(fixture(width_mm=10000.0))

    def test_nonnegative_cost_and_time_inputs_reject_negative(self):
        for field in ("setup_minutes", "noncut_minutes", "tool_change_minutes",
                      "machine_rate_hour", "tool_cost", "other_cost_per_part", "other_batch_cost"):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    validate_scenario(fixture(**{field: -0.01}))

    def test_integer_quantities_reject_bool_fraction_zero_and_negative(self):
        for field in ("passes", "teeth", "insert_positions", "demand_qty", "starts"):
            for value in (True, False, 1.5, 0, -1):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValueError):
                        validate_scenario(fixture(**{field: value}))

    def test_boolean_is_not_a_numeric_parameter(self):
        for field in ("diameter_mm", "tool_cost", "efficiency", "available_minutes"):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    validate_scenario(fixture(**{field: True}))

    def test_efficiency_and_grid_bounds_are_validated(self):
        invalids = ({"efficiency": 1.01}, {"rpm_min": 10001.0},
                    {"speed_min": 1001.0}, {"baseline_speed": 1001.0})
        for changes in invalids:
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    validate_scenario(fixture(**changes))
        with self.assertRaises(ValueError):
            speed_grid(fixture(speed_resolution=0.0001))

    def test_invalid_labels_and_unattributed_production_profile_rejected(self):
        invalids = ({"operation": "grinding"}, {"tool_type": "unknown"},
                    {"calibration_kind": "estimated"},
                    {"calibration_kind": "measured", "calibration_source": " "},
                    {"calibration_kind": "supplier", "calibration_source": ""})
        for changes in invalids:
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    validate_scenario(fixture(**changes))

    def test_demonstration_profiles_are_explicit(self):
        for operation in ("turning", "milling"):
            s = demo_scenario(operation)
            validate_scenario(s)
            self.assertEqual(s.operation, operation)
            self.assertEqual(s.calibration_kind, "demonstration")
            self.assertTrue(s.calibration_source.strip())


class HillClimbingAcceptanceTests(unittest.TestCase):
    """R06: deterministic bounded hill climbing and independent small oracles."""

    def test_speed_grid_includes_upper_endpoint_once(self):
        s = fixture(speed_min=80.0, speed_max=91.0, baseline_speed=85.0,
                    speed_resolution=3.0)
        self.assertEqual(speed_grid(s), (80.0, 83.0, 86.0, 89.0, 91.0))

    def test_distinct_adjacent_float_endpoints_are_preserved(self):
        upper = math.nextafter(80.0, math.inf)
        s = fixture(speed_min=80.0, speed_max=upper, baseline_speed=80.0,
                    speed_resolution=3.0)
        self.assertEqual(speed_grid(s), (80.0, upper))

    def test_maximum_grid_includes_both_endpoints_within_limit(self):
        s = fixture(speed_min=100.0, speed_max=20100.0, baseline_speed=150.0,
                    speed_resolution=1.0)
        grid = speed_grid(s)
        self.assertEqual(len(grid), 20001)
        self.assertEqual((grid[0], grid[-1]), (100.0, 20100.0))
        with self.assertRaises(ValueError):
            speed_grid(replace(s, speed_max=20100.5))

    def test_equal_cost_ties_and_search_trace_are_repeatable(self):
        s = fixture(speed_min=40.0, speed_max=100.0, baseline_speed=63.0,
                    speed_resolution=3.0, machine_rate_hour=0.0, tool_cost=0.0,
                    other_cost_per_part=2.0, other_batch_cost=5.0)
        first, second = optimize(s), optimize(s)
        self.assertEqual(first.best, second.best)
        self.assertEqual(first.baseline, second.baseline)
        self.assertEqual(first.evaluations, second.evaluations)
        self.assertEqual(first.trace, second.trace)
        self.assertIsNotNone(first.best)
        self.assertAlmostEqual(first.best.unit_cost, 2.2)

    def test_feasible_off_grid_baseline_is_preserved(self):
        s = fixture(speed_min=250.0, speed_max=400.0, baseline_speed=314.1592653589793,
                    speed_resolution=25.0, starts=3)
        result = optimize(s)
        self.assertTrue(result.baseline.feasible)
        self.assertIsNotNone(result.best)
        self.assertLessEqual(result.best.unit_cost, result.baseline.unit_cost)

    def test_small_discrete_domains_match_independent_exhaustive_oracle(self):
        # Eleven starts for eleven points deliberately covers disconnected
        # local minima while exercising the optimizer's baseline comparison,
        # feasibility, tie ordering and discrete economics. This is a bounded
        # acceptance comparison, never a global-optimality guarantee.
        for demand in (1, 11, 25, 83):
            with self.subTest(demand=demand):
                s = fixture(demand_qty=demand, speed_min=100.0, speed_max=200.0,
                            baseline_speed=157.0, speed_resolution=10.0, starts=11,
                            v_ref_m_min=150.0, life_ref_min=5.0,
                            cut_length_mm=25.0, passes=1)
                independently_enumerated = [100.0 + 10.0 * index for index in range(11)] + [157.0]
                costs = [independent_turning_cost(s, speed)[0]
                         for speed in independently_enumerated
                         if independent_turning_cost(s, speed)[1]]
                result = optimize(s)
                self.assertIsNotNone(result.best)
                self.assertAlmostEqual(result.best.unit_cost, min(costs), places=11)
                self.assertTrue(independent_turning_cost(s, result.best.speed_m_min)[1])

    def test_single_start_reaches_monotone_optimum(self):
        # One fresh tool always suffices; shorter cutting time strictly lowers
        # cost. The optimum is a known boundary; starts=1 also retains the
        # algorithm's required endpoint and baseline seeds.
        s = fixture(demand_qty=1, speed_min=100.0, speed_max=200.0,
                    baseline_speed=150.0, speed_resolution=10.0, starts=1,
                    life_ref_min=1000.0)
        result = optimize(s)
        self.assertEqual(result.best.speed_m_min, 200.0)
        cost, feasible = independent_turning_cost(s, 200.0)
        self.assertTrue(feasible)
        self.assertAlmostEqual(result.best.unit_cost, cost, places=11)
        self.assertTrue(any(event["event"] == "move" for event in result.trace))
        previous_cost = {}
        refinement_steps = {}
        for event in result.trace:
            restart = event["restart"]
            if event["event"] == "start":
                previous_cost[restart] = event["unit_cost"]
            elif event["event"] == "move":
                self.assertLess(event["unit_cost"], previous_cost[restart])
                previous_cost[restart] = event["unit_cost"]
            elif event["event"] == "refine":
                refinement_steps.setdefault(restart, []).append(event["step"])
        for steps in refinement_steps.values():
            self.assertEqual(steps[-1], 1)
            self.assertTrue(all(later == earlier // 2 for earlier, later in zip(steps, steps[1:])))

    def test_feasibility_fallback_does_not_miss_narrow_rpm_interval(self):
        # At D100 only v=130 of these 31 grid speeds meets the RPM interval.
        # Search starts at 100, 250, 400 cannot see this narrow feasible island
        # directly; the approved fallback must still discover a feasible point.
        rpm_at_130 = 130000.0 / (math.pi * 100.0)
        s = fixture(speed_min=100.0, speed_max=400.0, baseline_speed=250.0,
                    speed_resolution=10.0, starts=3,
                    rpm_min=rpm_at_130 - 0.01, rpm_max=rpm_at_130 + 0.01)
        result = optimize(s)
        self.assertIsNotNone(result.best)
        self.assertTrue(result.best.feasible)
        self.assertEqual(result.best.speed_m_min, 130.0)

    def test_returned_evaluations_stay_in_bounded_domain(self):
        s = fixture(speed_min=100.0, speed_max=200.0, baseline_speed=157.0,
                    speed_resolution=10.0, starts=3)
        result = optimize(s)
        permitted = set(speed_grid(s)) | {s.baseline_speed}
        self.assertEqual(result.grid_size, 11)
        self.assertTrue(result.evaluations)
        self.assertTrue(all(e.speed_m_min in permitted for e in result.evaluations))
        self.assertLessEqual(len(result.evaluations), len(permitted))


class BusinessSeparationTests(unittest.TestCase):
    """R08: the business evaluator must remain usable without UI/search."""

    def test_business_module_does_not_import_ui_or_search(self):
        tree = ast.parse(inspect.getsource(engine))
        imported_names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_names.extend(item.name for item in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported_names.append(node.module or "")
                imported_names.extend(item.name for item in node.names)
        forbidden = {"tkinter", "ui", "search", "tool_life_optimizer.ui", "tool_life_optimizer.search"}
        self.assertFalse(forbidden.intersection(imported_names))


if __name__ == "__main__":
    unittest.main()
