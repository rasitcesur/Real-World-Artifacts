"""Run immutable acceptance vectors and write machine-readable evidence."""
import io
import json
import platform
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    evidence = {
        "requirement_id": "REQ-TOOL-LIFE-001", "unified_execution_plan_id": "UEP-TOOL-LIFE-001-v1",
        "timestamp": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
        "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
        "skipped": len(result.skipped), "passed": result.wasSuccessful(),
        "test_log": stream.getvalue(),
    }
    outputs = ROOT / "outputs"
    outputs.mkdir(exist_ok=True)
    (outputs / "verification_report.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(stream.getvalue())
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
