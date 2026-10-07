"""Executable desktop acceptance checks and screenshots for R07.

Run from the project root: python tests/gui_smoke.py
Screenshots require Pillow for QA only; the delivered app needs no Pillow.
"""
import ctypes
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tool_life_optimizer.engine import demo_scenario
from tool_life_optimizer.persistence import export_result_csv, export_result_json, load_scenario, save_scenario
from tool_life_optimizer.ui import OptimizerApp


def pump(app, predicate=lambda: True, timeout=20):
    deadline = time.monotonic() + timeout
    while True:
        app.update()
        if predicate():
            return
        if time.monotonic() > deadline:
            raise AssertionError("GUI operation timed out")
        time.sleep(.03)


def capture(app, path):
    from PIL import ImageGrab
    from ctypes import wintypes
    get_ancestor = ctypes.windll.user32.GetAncestor
    get_ancestor.argtypes = (wintypes.HWND, wintypes.UINT)
    get_ancestor.restype = wintypes.HWND
    hwnd = get_ancestor(app.winfo_id(), 2)
    app.lift()
    app.update()
    time.sleep(.15)
    ImageGrab.grab(window=hwnd).save(path)


def main():
    outputs = ROOT / "outputs"
    examples = ROOT / "examples"
    outputs.mkdir(exist_ok=True)
    examples.mkdir(exist_ok=True)
    checks = []
    app = OptimizerApp()
    try:
        app.geometry("1500x960+10+10")
        pump(app)
        checks.append({"check": "desktop_start", "passed": True,
                       "screen": [app.winfo_screenwidth(), app.winfo_screenheight()]})
        for operation in ("turning", "milling"):
            app.mode.set(operation)
            if app.current_mode != operation:
                app._switch_mode()
            app.run_optimization()
            pump(app, lambda: not app._busy)
            assert app.result is not None and app.result.best is not None
            assert len(app.comparison.get_children()) == 7
            assert str(app.json_button.cget("state")) == "normal"
            assert app.metric_values["speed"].get() != "—"
            result = app.result
            checks.append({"check": operation + "_optimize", "passed": True,
                           "speed": result.best.speed_m_min, "cost": result.best.unit_cost})
            save_scenario(examples / (operation + "_demo.json"), result.scenario)
            assert load_scenario(examples / (operation + "_demo.json")) == result.scenario
            export_result_json(examples / (operation + "_demo_result.json"), result)
            export_result_csv(examples / (operation + "_demo_result.csv"), result)
            capture(app, outputs / (operation + "_ui.png"))
            checks.append({"check": operation + "_save_export", "passed": True})
            app.vars["demand_qty"].set("201")
            assert app.result is None and str(app.json_button.cget("state")) == "disabled"
            checks.append({"check": operation + "_stale_result_blocked", "passed": True})

        # Separate-mode drafts keep their own edits; source curves cannot transfer silently.
        app.mode.set("turning")
        app._switch_mode()
        assert app.vars["demand_qty"].get() == "201"
        assert app.vars["v_ref_m_min"].get() == "180.0"
        app.mode.set("milling")
        app._switch_mode()
        assert app.vars["v_ref_m_min"].get() == "140.0"
        checks.append({"check": "independent_mode_drafts", "passed": True})

        app._fill(demo_scenario("milling"))
        app.geometry("1200x800+10+10")
        pump(app)
        app.run_optimization()
        pump(app, lambda: not app._busy)
        capture(app, outputs / "milling_ui_1200x800.png")
        # Every tab can be selected and every form has a working scrolling region.
        for index in range(4):
            app.inputs.select(index)
            pump(app)
            page = app.inputs.nametowidget(app.inputs.tabs()[index])
            page.canvas.yview_moveto(1)
            pump(app)
            assert page.content.winfo_width() > 300
        checks.append({"check": "compact_layout_and_all_input_tabs", "passed": True})
        app.inputs.select(3)
        capture(app, outputs / "machine_limits_ui.png")
        app.result_tabs.select(1)
        pump(app)
        assert app.trace_tree.get_children()
        app.result_tabs.select(2)
        pump(app)
        checks.append({"check": "trace_and_model_tabs", "passed": True})

        app._fill(replace(demo_scenario("turning"), available_minutes=.01))
        app.run_optimization()
        pump(app, lambda: not app._busy)
        assert app.result is not None and app.result.best is None
        assert "No feasible" in app.feasibility.cget("text")
        checks.append({"check": "infeasible_demand_message", "passed": True})
        app._material_reference()
        pump(app)
        popups = [child for child in app.winfo_children() if child.winfo_class() == "Toplevel"]
        assert popups
        checks.append({"check": "material_reference_dialog", "passed": True})
        for child in popups:
            child.destroy()
    finally:
        app.destroy()
    report = {"requirement": "R07", "checks": checks, "passed": all(row["passed"] for row in checks)}
    (outputs / "gui_verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
