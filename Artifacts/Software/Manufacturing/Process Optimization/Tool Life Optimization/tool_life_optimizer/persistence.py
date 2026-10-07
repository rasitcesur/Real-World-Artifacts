"""Versioned JSON scenarios and traceable, finite JSON/CSV run exports."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import asdict, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .engine import Scenario, validate_scenario

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_VERSION = "1.0.0"


def finite_data(value: Any) -> Any:
    """JSON exports represent unavailable numeric results as null, never Infinity."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: finite_data(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [finite_data(item) for item in value]
    return value


def payload_hash(payload: Any) -> str:
    canonical = json.dumps(finite_data(payload), sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"), allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def file_hash(path: Path) -> str | None:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def save_scenario(path: str | Path, scenario: Scenario) -> None:
    validate_scenario(scenario)
    data = {"schema_version": SCHEMA_VERSION, "scenario": asdict(scenario)}
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                          encoding="utf-8")


def load_scenario(path: str | Path) -> Scenario:
    def reject_constant(value: str) -> None:
        raise ValueError(f"Nonfinite JSON value is not permitted: {value}")
    data = json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=reject_constant)
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported scenario schema. Expected version 1.0.0.")
    raw = data.get("scenario")
    required = {field.name for field in fields(Scenario)}
    if not isinstance(raw, dict) or set(raw) != required:
        raise ValueError("Scenario fields do not match the versioned schema.")
    scenario = Scenario(**raw)
    validate_scenario(scenario)
    return scenario


def run_payload(result: Any) -> dict[str, Any]:
    return finite_data({
        "scenario": asdict(result.scenario), "algorithm": result.algorithm,
        "grid_size": result.grid_size, "message": result.message,
        "baseline": asdict(result.baseline),
        "best": asdict(result.best) if result.best is not None else None,
        "evaluations": [asdict(item) for item in result.evaluations],
        "trace": list(result.trace),
    })


def export_result_json(path: str | Path, result: Any) -> dict[str, Any]:
    payload = run_payload(result)
    digest = payload_hash(payload)
    provenance = {
        "artifact_id": "RUN-" + digest.split(":")[1][:16],
        "requirement_id": "REQ-TOOL-LIFE-001",
        "unified_execution_plan_id": "UEP-TOOL-LIFE-001-v1",
        "runtime_version": SCHEMA_VERSION,
        "canonical_algorithm": "urn:tool-life:deterministic-hill-climbing:1.0.0",
        "adapter_payload_hash": digest,
        "generation_timestamp": datetime.now(timezone.utc).isoformat(),
        "human_approvals": [{"date": "2026-10-06", "response": "YES",
                             "assumptions": ["A-001", "A-002", "A-003", "A-004", "A-005"]}],
        "assumption_log_entries": ["A-001", "A-002", "A-003", "A-004", "A-005"],
        "domain_expert_signatures": [], "provider_adapter_signatures": [],
        "knowledge_package_signatures": [],
        "verification_evidence_hash": file_hash(ROOT / "outputs" / "verification_report.json"),
        "requirements_hash": file_hash(ROOT / "requirements.md"),
        "unified_execution_plan_hash": file_hash(ROOT / "unified_execution_plan.json"),
        "identity_signature_status": "No authenticated identity signatures claimed",
    }
    data = {"schema_version": SCHEMA_VERSION, "run": payload, "ArtifactProvenance": provenance}
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                          encoding="utf-8")
    return data


def export_result_csv(path: str | Path, result: Any) -> None:
    fields_to_export = ["role", "operation", "currency", "speed_m_min", "spindle_rpm",
        "feed_mm_min", "cut_minutes", "predicted_life_minutes", "parts_per_tool",
        "tool_sets", "tool_changes", "batch_minutes", "cutting_power_kw", "motor_power_kw",
        "unit_cost", "machine_cost_per_part", "tooling_cost_per_part", "other_cost_per_part",
        "feasible", "violations"]
    with Path(path).open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields_to_export)
        writer.writeheader()
        rows = [("baseline", result.baseline)]
        if result.best is not None:
            rows.append(("selected", result.best))
        for role, evaluation in rows:
            row = finite_data(asdict(evaluation))
            row.update(role=role, operation=result.scenario.operation,
                       currency=result.scenario.currency)
            row["violations"] = "; ".join(evaluation.violations)
            writer.writerow({key: row.get(key) for key in fields_to_export})
