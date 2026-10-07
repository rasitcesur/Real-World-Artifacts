import csv
import json
import tempfile
import unittest
from dataclasses import asdict, replace
from pathlib import Path

from tool_life_optimizer.engine import demo_scenario
from tool_life_optimizer.persistence import (
    export_result_csv, export_result_json, load_scenario, payload_hash, save_scenario,
)
from tool_life_optimizer.search import optimize


class PersistenceAcceptanceTests(unittest.TestCase):
    def test_both_scenarios_round_trip_without_losing_parameters(self):
        with tempfile.TemporaryDirectory() as directory:
            for operation in ("turning", "milling"):
                with self.subTest(operation=operation):
                    scenario = replace(demo_scenario(operation), currency="TRY", name="Test çelik")
                    path = Path(directory) / (operation + ".json")
                    save_scenario(path, scenario)
                    self.assertEqual(load_scenario(path), scenario)

    def test_invalid_schema_and_missing_or_extra_fields_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            base = {"schema_version": "1.0.0", "scenario": asdict(demo_scenario())}
            cases = [{"schema_version": "2.0.0", "scenario": base["scenario"]},
                     {"schema_version": "1.0.0", "scenario": {"operation": "turning"}},
                     {"schema_version": "1.0.0", "scenario": dict(base["scenario"], extra="value")}]
            for case in cases:
                with self.subTest(case=case):
                    path.write_text(json.dumps(case), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_scenario(path)
            path.write_text('{"schema_version":"1.0.0","scenario":NaN}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_scenario(path)

    def test_json_export_provenance_binds_the_complete_deterministic_run(self):
        result = optimize(demo_scenario("milling"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.json"
            exported = export_result_json(path, result)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(exported, data)
            self.assertEqual(data["ArtifactProvenance"]["adapter_payload_hash"], payload_hash(data["run"]))
            self.assertEqual(data["ArtifactProvenance"]["requirement_id"], "REQ-TOOL-LIFE-001")
            self.assertEqual(len(data["ArtifactProvenance"]["human_approvals"][0]["assumptions"]), 5)
            self.assertTrue(data["run"]["trace"])
            self.assertEqual(data["run"]["best"]["speed_m_min"], result.best.speed_m_min)
            modified = dict(data["run"], message="altered")
            self.assertNotEqual(payload_hash(modified), data["ArtifactProvenance"]["adapter_payload_hash"])

    def test_infeasible_export_uses_null_instead_of_nonstandard_infinity(self):
        scenario = replace(demo_scenario(), life_ref_min=1e-6)
        result = optimize(scenario)
        self.assertIsNone(result.best)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "infeasible.json"
            export_result_json(path, result)
            raw = path.read_text(encoding="utf-8")
            self.assertNotIn("Infinity", raw)
            self.assertNotIn("NaN", raw)
            data = json.loads(raw)
            self.assertIsNone(data["run"]["baseline"]["unit_cost"])
            self.assertIsNone(data["run"]["best"])

    def test_csv_preserves_baseline_selected_roles_units_and_cost_breakdown(self):
        result = optimize(replace(demo_scenario(), currency="TRY"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.csv"
            export_result_csv(path, result)
            with path.open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([row["role"] for row in rows], ["baseline", "selected"])
            self.assertEqual(rows[1]["operation"], "turning")
            self.assertEqual(rows[1]["currency"], "TRY")
            self.assertEqual(rows[1]["feasible"], "True")
            self.assertAlmostEqual(float(rows[1]["unit_cost"]), sum(float(rows[1][key]) for key in
                                   ("machine_cost_per_part", "tooling_cost_per_part", "other_cost_per_part")))


if __name__ == "__main__":
    unittest.main()
