"""Tk desktop UI. Business calculations and search remain in separate modules."""
from __future__ import annotations

import math
import json
import queue
import threading
import tkinter as tk
import webbrowser
from dataclasses import asdict
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from .engine import Scenario, demo_scenario, evaluate, validate_scenario
from .persistence import export_result_csv, export_result_json, load_scenario, save_scenario
from .search import optimize, speed_grid

BG = "#f3f5f7"
WHITE = "#ffffff"
NAVY = "#182c3d"
TEAL = "#087f83"
MUTED = "#657583"
LINE = "#dbe2e8"
AMBER = "#925717"
RED = "#aa4040"

INTEGER_FIELDS = {"passes", "teeth", "insert_positions", "demand_qty", "starts"}
TEXT_FIELDS = {"name", "currency", "material_name", "hardness_label", "tool_name",
               "coolant", "calibration_kind", "calibration_source", "tool_type"}


class ScrollForm(ttk.Frame):
    def __init__(self, parent: Any):
        super().__init__(parent, style="White.TFrame")
        self.canvas = tk.Canvas(self, bg=WHITE, highlightthickness=0)
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.content = ttk.Frame(self.canvas, padding=(15, 12), style="White.TFrame")
        window = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.canvas.configure(yscrollcommand=scroll.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.content.bind("<Configure>", lambda event: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda event: self.canvas.itemconfigure(window, width=event.width))
        self.canvas.bind("<Enter>", lambda event: self.canvas.bind_all("<MouseWheel>", self._wheel))
        self.canvas.bind("<Leave>", lambda event: self.canvas.unbind_all("<MouseWheel>"))
        self.content.columnconfigure(1, weight=1)
        self.row = 0

    def _wheel(self, event: Any) -> None:
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def heading(self, text: str) -> None:
        ttk.Label(self.content, text=text, style="Section.TLabel").grid(
            row=self.row, column=0, columnspan=2, sticky="w", pady=(12 if self.row else 0, 9))
        self.row += 1

    def note(self, text: str) -> None:
        label = ttk.Label(self.content, text=text, style="Note.TLabel", wraplength=420, justify="left")
        label.grid(row=self.row, column=0, columnspan=2, sticky="ew", pady=(9, 8))
        self.row += 1


class OptimizerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Tool Life Optimizer")
        self.geometry("1500x960")
        self.minsize(1100, 740)
        self.configure(bg=BG)
        self._loading = True
        self._busy = False
        self.result = None
        self._plot_samples = []
        self._plot_hover = []
        self._messages: queue.Queue = queue.Queue()
        self.vars: dict[str, tk.StringVar] = {}
        self.widgets: dict[str, Any] = {}
        self.field_labels: dict[str, Any] = {}
        self._mode_cache: dict[str, dict[str, str]] = {}
        self.current_mode = "turning"
        self.mode = tk.StringVar(value="turning")
        self.status = tk.StringVar(value="Ready. Demonstration inputs are loaded.")
        self.plot_hint = tk.StringVar(value="Run optimization to compare cutting speed, cost and tool life.")
        self._styles()
        self._build()
        self._fill(demo_scenario("turning"))
        self._loading = False
        for var in self.vars.values():
            var.trace_add("write", self._input_changed)
        self._update_fields()
        self.after(100, self._poll)

    def _styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("White.TFrame", background=WHITE)
        style.configure("TLabel", background=WHITE, foreground=NAVY, font=("Segoe UI", 10))
        style.configure("Section.TLabel", font=("Segoe UI", 10, "bold"), foreground=TEAL)
        style.configure("Note.TLabel", font=("Segoe UI", 9), foreground=MUTED)
        style.configure("TEntry", padding=5, fieldbackground=WHITE, bordercolor=LINE)
        style.configure("TCombobox", padding=5, fieldbackground=WHITE)
        style.configure("TButton", padding=(12, 7), font=("Segoe UI", 10), background="#e8edf1")
        style.configure("Accent.TButton", background=TEAL, foreground=WHITE, font=("Segoe UI", 11, "bold"))
        style.map("Accent.TButton", background=[("active", "#07676a"), ("disabled", "#a9bdc3")])
        style.configure("TNotebook", background=WHITE, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(12, 9), font=("Segoe UI", 10))
        style.map("TNotebook.Tab", background=[("selected", WHITE)], foreground=[("selected", TEAL)])
        style.configure("Treeview", font=("Segoe UI", 10), rowheight=30, background=WHITE,
                        fieldbackground=WHITE, borderwidth=0)
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"), background="#edf2f4")

    def _build(self) -> None:
        header = tk.Frame(self, bg=NAVY, padx=24, pady=15)
        header.pack(fill="x")
        tk.Label(header, text="Tool Life Optimizer", font=("Segoe UI", 20, "bold"),
                 fg=WHITE, bg=NAVY).pack(side="left")
        tk.Label(header, text="Turning and milling economics", font=("Segoe UI", 11),
                 fg="#c8d5df", bg=NAVY).pack(side="right")

        self.banner = tk.Label(self, text="DEMONSTRATION PROFILE   Synthetic tool-life inputs. Enter calibrated data for production decisions.",
                               bg="#fff0d9", fg=AMBER, font=("Segoe UI", 10), anchor="w", padx=24, pady=9)
        self.banner.pack(fill="x")
        panes = ttk.Panedwindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=18, pady=16)
        left = ttk.Frame(panes, style="White.TFrame", padding=(0, 0, 0, 8))
        right = ttk.Frame(panes, style="White.TFrame", padding=18)
        panes.add(left, weight=0)
        panes.add(right, weight=1)
        self.after_idle(lambda: panes.sashpos(0, 500))

        toolbar = ttk.Frame(left, style="White.TFrame", padding=(15, 12))
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="Operation", font=("Segoe UI", 10, "bold")).pack(side="left", padx=(0, 9))
        self.mode_combo = ttk.Combobox(toolbar, textvariable=self.mode, values=("turning", "milling"),
                                       state="readonly", width=10)
        self.mode_combo.pack(side="left")
        self.mode_combo.bind("<<ComboboxSelected>>", self._switch_mode)
        ttk.Button(toolbar, text="Open", command=self._open).pack(side="right", padx=(5, 0))
        ttk.Button(toolbar, text="Save", command=self._save).pack(side="right")
        self.inputs = ttk.Notebook(left)
        self.inputs.pack(fill="both", expand=True)
        job, operation, life, costs = [ScrollForm(self.inputs) for _ in range(4)]
        for page, title in zip((job, operation, life, costs), ("Job", "Operation", "Tool life", "Costs / limits")):
            self.inputs.add(page, text=title)

        job.heading("Production demand")
        self._field(job, "name", "Scenario name")
        self._field(job, "demand_qty", "Batch demand (parts)")
        self._field(job, "available_minutes", "Available machine time (min)")
        self._field(job, "currency", "Currency / cost unit")
        job.note("Leave available time blank for no deadline. Enter effective machine minutes allocated to this operation.")
        job.heading("Material and tooling context")
        ttk.Button(job.content, text="Metal reference data", command=self._material_reference).grid(
            row=job.row, column=0, columnspan=2, sticky="w", pady=(0, 8))
        job.row += 1
        self._field(job, "material_name", "Alloy / material condition")
        self._field(job, "hardness_label", "Hardness and scale")
        self._field(job, "tool_name", "Tool / insert grade")
        self._field(job, "coolant", "Coolant condition")
        self._field(job, "tool_type", "Milling cutter type", ("indexable", "solid"))
        job.note("Each scenario evaluates one operation. Turning and milling retain separate input drafts and life profiles.")

        operation.heading("Fixed cutting geometry")
        self._field(operation, "diameter_mm", "Effective diameter (mm)")
        self._field(operation, "cut_length_mm", "Engaged length per pass (mm)")
        self._field(operation, "passes", "Number of identical passes")
        self._field(operation, "feed_turn_mm_rev", "Turning feed (mm/rev)")
        self._field(operation, "feed_mill_mm_tooth", "Milling feed per tooth (mm)")
        self._field(operation, "teeth", "Effective milling feed teeth")
        self._field(operation, "insert_positions", "Physical milling insert positions")
        self._field(operation, "depth_mm", "Cutting / axial depth (mm)")
        self._field(operation, "width_mm", "Milling radial engagement (mm)")
        self._field(operation, "specific_force_n_mm2", "Effective cutting force kc (N/mm²)")
        operation.note("Feed, depths and engagement stay fixed. Milling length includes cutting moves only. Turning uses the entered effective diameter throughout the modeled passes.")
        operation.note("Enter effective kc for the actual chip thickness and geometry. Material kc1 reference values require conversion.")

        life.heading("Independent tool-life calibration")
        self._field(life, "calibration_kind", "Calibration origin", ("demonstration", "measured", "supplier"))
        self._field(life, "calibration_source", "Source / test reference")
        self._field(life, "v_ref_m_min", "Reference cutting speed (m/min)")
        self._field(life, "life_ref_min", "Life at reference speed (min)")
        self._field(life, "taylor_exponent", "Taylor exponent b")
        life.note("T(v) = Tref × (vref / v)^(1/b). Life is accumulated cutter-in-cut clock time at matching material, tool, feed, engagement and coolant conditions.")
        life.heading("Permitted speed and search")
        self._field(life, "speed_min", "Minimum cutting speed (m/min)")
        self._field(life, "speed_max", "Maximum cutting speed (m/min)")
        self._field(life, "baseline_speed", "Current / baseline speed (m/min)")
        self._field(life, "speed_resolution", "Search resolution (m/min)")
        self._field(life, "starts", "Hill-climbing starting points")
        life.note("Use a quality-qualified speed range. Multiple starts and smaller steps improve exploration. The result is the best feasible point found.")

        costs.heading("Batch economics")
        for key, label in (
            ("machine_rate_hour", "Machine, labor and overhead (CU/h)"),
            ("tool_cost", "Usable edge / whole cutter cost (CU)"),
            ("other_cost_per_part", "Other production cost (CU/part)"),
            ("other_batch_cost", "Other fixed batch cost (CU)"),
            ("setup_minutes", "Initial batch setup (min)"),
            ("noncut_minutes", "Noncutting time per part (min)"),
            ("tool_change_minutes", "Edge / cutter-set change (min)"),
        ):
            self._field(costs, key, label)
        costs.note("CU uses the currency or cost unit entered on Job. Turning charges a usable edge. Indexable milling multiplies edge cost by physical positions. Solid milling charges one whole cutter. Fresh-tool installation belongs to setup.")
        costs.heading("Hard machine limits")
        for key, label in (
            ("rpm_min", "Minimum spindle speed (rpm)"),
            ("rpm_max", "Maximum spindle speed (rpm)"),
            ("axis_feed_max_mm_min", "Maximum axis feed (mm/min)"),
            ("motor_power_kw", "Available motor power (kW)"),
            ("efficiency", "Spindle efficiency (0 to 1)"),
        ):
            self._field(costs, key, label)
        costs.note("Every allocated edge or cutter set receives a full charge. Index between completed parts. A single edge/set must finish one part.")

        actions = ttk.Frame(left, style="White.TFrame", padding=(15, 12, 15, 2))
        actions.pack(fill="x")
        self.optimize_button = ttk.Button(actions, text="Optimize", style="Accent.TButton", command=self.run_optimization)
        self.optimize_button.pack(side="left", fill="x", expand=True)
        self.reset_button = ttk.Button(actions, text="Load demo", command=self._reset)
        self.reset_button.pack(side="left", padx=(9, 0))

        top = ttk.Frame(right, style="White.TFrame")
        top.pack(fill="x")
        ttk.Label(top, text="Selected operating point", font=("Segoe UI", 15, "bold")).pack(side="left")
        self.csv_button = ttk.Button(top, text="Export CSV", command=lambda: self._export("csv"), state="disabled")
        self.csv_button.pack(side="right", padx=(5, 0))
        self.json_button = ttk.Button(top, text="Export JSON", command=lambda: self._export("json"), state="disabled")
        self.json_button.pack(side="right")

        metrics = ttk.Frame(right, style="White.TFrame")
        metrics.pack(fill="x", pady=(18, 14))
        self.metric_values = {}
        self.metric_units = {}
        for i, (key, label, unit) in enumerate((
            ("speed", "CUTTING SPEED", "m/min"), ("life", "PREDICTED TOOL LIFE", "cutting min"),
            ("cost", "UNIT PRODUCTION COST", "CU/part"), ("time", "BATCH MACHINE TIME", "min"))):
            card = tk.Frame(metrics, bg="#f2f6f8", padx=12, pady=12)
            card.grid(row=0, column=i, sticky="nsew", padx=(0, 8 if i < 3 else 0))
            metrics.columnconfigure(i, weight=1, uniform="metric")
            tk.Label(card, text=label, font=("Segoe UI", 8, "bold"), fg=MUTED,
                     bg="#f2f6f8", anchor="w").pack(fill="x")
            value = tk.StringVar(value="—")
            unit_var = tk.StringVar(value=unit)
            tk.Label(card, textvariable=value, font=("Segoe UI", 23, "bold"), fg=TEAL,
                     bg="#f2f6f8", anchor="w").pack(fill="x", pady=(6, 0))
            tk.Label(card, textvariable=unit_var, font=("Segoe UI", 9), fg=MUTED,
                     bg="#f2f6f8", anchor="w").pack(fill="x")
            self.metric_values[key] = value
            self.metric_units[key] = unit_var
        self.feasibility = tk.Label(right, text="Enter a scenario and run optimization.", fg=MUTED,
                                    bg=WHITE, font=("Segoe UI", 10), anchor="w", justify="left")
        self.feasibility.pack(fill="x", pady=(0, 11))
        right.bind("<Configure>", lambda event: self.feasibility.configure(wraplength=max(300, event.width - 36)))

        self.comparison = ttk.Treeview(right, columns=("metric", "baseline", "selected"),
                                      show="headings", height=7, selectmode="none")
        for key, title, width in (("metric", "Comparison", 230), ("baseline", "Baseline", 150),
                                  ("selected", "Selected", 150)):
            self.comparison.heading(key, text=title)
            self.comparison.column(key, width=width, minwidth=85,
                                   anchor="w" if key == "metric" else "e", stretch=True)
        self.comparison.pack(fill="x")

        results = ttk.Notebook(right)
        results.pack(fill="both", expand=True, pady=(15, 0))
        plot = ttk.Frame(results, style="White.TFrame")
        trace_page = ttk.Frame(results, style="White.TFrame")
        model = ttk.Frame(results, style="White.TFrame")
        results.add(plot, text="Cost and tool life")
        results.add(trace_page, text="Search record")
        results.add(model, text="Model and sources")
        self.result_tabs = results
        ttk.Label(plot, textvariable=self.plot_hint, style="Note.TLabel", wraplength=800).pack(fill="x", padx=10, pady=8)
        self.chart = tk.Canvas(plot, bg=WHITE, highlightthickness=0)
        self.chart.pack(fill="both", expand=True)
        self.chart.bind("<Configure>", lambda event: self._draw_chart())
        self.chart.bind("<Motion>", self._hover_chart)
        self.trace_tree = ttk.Treeview(trace_page, columns=("event", "details"), show="headings")
        self.trace_tree.heading("event", text="Step / event")
        self.trace_tree.heading("details", text="Recorded decision")
        self.trace_tree.column("event", width=130, stretch=False)
        self.trace_tree.column("details", width=600, stretch=True)
        trace_scroll = ttk.Scrollbar(trace_page, orient="vertical", command=self.trace_tree.yview)
        self.trace_tree.configure(yscrollcommand=trace_scroll.set)
        self.trace_tree.pack(side="left", fill="both", expand=True)
        trace_scroll.pack(side="right", fill="y")
        text = tk.Text(model, wrap="word", bg=WHITE, fg=NAVY, font=("Segoe UI", 10),
                       relief="flat", padx=16, pady=15)
        text.pack(fill="both", expand=True)
        text.insert("end", "MODEL\n\n")
        text.insert("end", "Turning: RPM = 1000v / (πD). Feed rate = feed/rev × RPM.\n"
                    "Milling: feed rate = feed/tooth × effective teeth × RPM.\n"
                    "Cutting time = engaged length × identical passes / feed rate.\n"
                    "Tool life = reference life × (reference speed / v)^(1/b).\n\n"
                    "Parts per edge/set = floor(tool life / cutting time).\n"
                    "Allocated sets = ceiling(batch demand / parts per set).\n"
                    "Changes = allocated sets − 1.\n"
                    "Batch time = setup + demand × (cutting + noncutting) + changes × change time.\n"
                    "Unit cost = machine + allocated tooling + entered other production costs.\n\n"
                    "INTERPRETATION\n\n"
                    "Fresh tooling and full set charges apply. Changes occur between parts. "
                    "Milling life uses cutter-in-cut clock minutes and a separately calibrated curve. "
                    "Physical insert positions set tool cost; effective teeth set feed. "
                    "Available time is allocated effective machine time. "
                    "Speed bounds should already satisfy your process-quality requirements.\n\n"
                    "Hill climbing reports the best feasible grid point found. It does not guarantee "
                    "a global or continuous optimum. Demo data does not establish actual wear, "
                    "surface quality, sudden-fracture risk or realized production savings.\n\n"
                    "SOURCES\n\n")
        sources = (
            ("Sandvik turning equations", "https://www.sandvik.coromant.com/en-gb/knowledge/machining-formulas-definitions/general-turning-formulas-definitions"),
            ("Sandvik milling equations", "https://www.sandvik.coromant.com/en-gb/knowledge/machining-formulas-definitions/milling-formulas-definitions"),
            ("Material classification and hardness", "https://www.sandvik.coromant.com/en-gb/knowledge/materials/workpiece-materials"),
            ("Specific cutting force", "https://www.sandvik.coromant.com/en-gb/knowledge/materials/specific-cutting-force"),
            ("Source Drive folder", "https://drive.google.com/drive/folders/186Bdzhf5zeGFonGZ9KiwWImWFUA3vejY"),
        )
        for i, (label, url) in enumerate(sources):
            tag = f"link{i}"
            text.insert("end", label + "\n", tag)
            text.tag_configure(tag, foreground=TEAL, underline=True)
            text.tag_bind(tag, "<Button-1>", lambda event, target=url: webbrowser.open(target))
        text.configure(state="disabled")
        footer = tk.Frame(self, bg="#e6ecef", padx=20, pady=8)
        footer.pack(fill="x")
        tk.Label(footer, textvariable=self.status, bg="#e6ecef", fg=NAVY,
                 font=("Segoe UI", 9), anchor="w").pack(fill="x")

    def _field(self, page: ScrollForm, key: str, label: str, values: tuple | None = None) -> None:
        var = tk.StringVar()
        self.vars[key] = var
        field_label = ttk.Label(page.content, text=label, wraplength=270)
        field_label.grid(row=page.row, column=0, sticky="w", pady=5, padx=(0, 9))
        self.field_labels[key] = field_label
        if values:
            widget = ttk.Combobox(page.content, textvariable=var, values=values, state="readonly", width=18)
        else:
            widget = ttk.Entry(page.content, textvariable=var, width=20)
        widget.grid(row=page.row, column=1, sticky="ew", pady=5)
        self.widgets[key] = widget
        page.row += 1

    def _fill(self, scenario: Scenario) -> None:
        self._loading = True
        self.current_mode = scenario.operation
        self.mode.set(scenario.operation)
        for key, value in asdict(scenario).items():
            if key in self.vars:
                self.vars[key].set("" if value is None else str(value))
        self._loading = False
        self._update_fields()

    def _scenario(self) -> Scenario:
        data = {"operation": self.mode.get()}
        for key, var in self.vars.items():
            raw = var.get().strip()
            try:
                if key in TEXT_FIELDS:
                    data[key] = raw
                elif key in INTEGER_FIELDS:
                    data[key] = int(raw)
                elif key == "available_minutes" and raw == "":
                    data[key] = None
                else:
                    data[key] = float(raw)
            except ValueError as error:
                raise ValueError(f"Invalid value for {key.replace('_', ' ')}.") from error
        scenario = Scenario(**data)
        validate_scenario(scenario)
        return scenario

    def _update_fields(self) -> None:
        if not self.widgets:
            return
        milling = self.mode.get() == "milling"
        self.field_labels["diameter_mm"].configure(text="Effective cutter diameter (mm)" if milling else "Machined diameter (mm)")
        self.field_labels["cut_length_mm"].configure(text="Engaged toolpath per pass (mm)" if milling else "Cutting length per pass (mm)")
        self.field_labels["tool_cost"].configure(text=("Whole cutter cost (CU)" if self.vars["tool_type"].get() == "solid"
                                                     else "Cost per usable insert edge (CU)") if milling else "Cost per usable turning edge (CU)")
        for key in ("feed_mill_mm_tooth", "teeth", "insert_positions", "width_mm", "tool_type"):
            self.widgets[key].configure(state=("readonly" if key == "tool_type" else "normal") if milling else "disabled")
        self.widgets["feed_turn_mm_rev"].configure(state="disabled" if milling else "normal")
        if milling and self.vars["tool_type"].get() == "solid":
            self.widgets["insert_positions"].configure(state="disabled")
        demo = self.vars["calibration_kind"].get() == "demonstration"
        self.banner.configure(
            text="DEMONSTRATION PROFILE   Synthetic tool-life inputs. Enter calibrated data for production decisions." if demo
                 else "CALIBRATED PROFILE   Confirm that the source matches material, tool, feed, engagement and coolant.",
            bg="#fff0d9" if demo else "#e5f3ef", fg=AMBER if demo else TEAL)

    def _input_changed(self, *args: Any) -> None:
        if self._loading:
            return
        self._update_fields()
        self._invalidate("Inputs changed. Run optimization to update the result.")

    def _invalidate(self, message: str) -> None:
        self.result = None
        self._plot_samples = []
        self.json_button.configure(state="disabled")
        self.csv_button.configure(state="disabled")
        for value in self.metric_values.values():
            value.set("—")
        for tree in (self.comparison, self.trace_tree):
            tree.delete(*tree.get_children())
        self.feasibility.configure(text="Result pending for current inputs.", fg=MUTED)
        self.status.set(message)
        self.plot_hint.set("Run optimization to compare cutting speed, cost and tool life.")
        self._draw_chart()

    def _switch_mode(self, event: Any = None) -> None:
        if self._busy:
            self.mode.set(self.current_mode)
            return
        self._mode_cache[self.current_mode] = {key: var.get() for key, var in self.vars.items()}
        target = self.mode.get()
        if target in self._mode_cache:
            self._loading = True
            for key, value in self._mode_cache[target].items():
                self.vars[key].set(value)
            self.current_mode = target
            self._loading = False
            self._update_fields()
        else:
            self._fill(demo_scenario(target))
        self._invalidate(f"{target.title()} scenario loaded. Run optimization.")

    def _reset(self) -> None:
        if not self._busy:
            self._fill(demo_scenario(self.mode.get()))
            self._invalidate("Synthetic demonstration inputs restored.")

    def run_optimization(self) -> None:
        if self._busy:
            return
        try:
            scenario = self._scenario()
        except (ValueError, TypeError) as error:
            self.status.set(str(error))
            messagebox.showerror("Check scenario inputs", str(error), parent=self)
            return
        self._busy = True
        self.optimize_button.configure(state="disabled")
        self.reset_button.configure(state="disabled")
        self.mode_combo.configure(state="disabled")
        self.status.set("Evaluating demand, tooling and machine constraints...")
        snapshot = {key: var.get() for key, var in self.vars.items()}

        def work() -> None:
            try:
                result = optimize(scenario)
                domain = speed_grid(scenario)
                stride = max(1, math.ceil(len(domain) / 350))
                sample_speeds = set(domain[::stride]) | {domain[-1], scenario.baseline_speed}
                if result.best is not None:
                    sample_speeds.add(result.best.speed_m_min)
                samples = [evaluate(scenario, value) for value in sorted(sample_speeds)]
                self._messages.put(("ok", result, samples, snapshot))
            except Exception as error:
                self._messages.put(("error", str(error)))
        threading.Thread(target=work, daemon=True).start()

    def _poll(self) -> None:
        try:
            while True:
                message = self._messages.get_nowait()
                self._busy = False
                self.optimize_button.configure(state="normal")
                self.reset_button.configure(state="normal")
                self.mode_combo.configure(state="readonly")
                if message[0] == "error":
                    self.status.set(message[1])
                    messagebox.showerror("Optimization error", message[1], parent=self)
                elif message[3] != {key: var.get() for key, var in self.vars.items()}:
                    self._invalidate("Inputs changed during the run. Optimize the current inputs.")
                else:
                    self.display_result(message[1], message[2])
        except queue.Empty:
            pass
        self.after(100, self._poll)

    @staticmethod
    def _number(value: float, digits: int = 2) -> str:
        return f"{value:,.{digits}f}" if math.isfinite(value) else "Unavailable"

    def display_result(self, result: Any, samples: list | None = None) -> None:
        self.result = result
        self._plot_samples = samples or list(result.evaluations)
        self.comparison.delete(*self.comparison.get_children())
        self.trace_tree.delete(*self.trace_tree.get_children())
        self.json_button.configure(state="normal")
        self.csv_button.configure(state="normal")
        base, selected, s = result.baseline, result.best, result.scenario
        self.metric_units["cost"].set(f"{s.currency}/part")
        if selected is not None:
            for key, value in (("speed", selected.speed_m_min), ("life", selected.predicted_life_minutes),
                               ("cost", selected.unit_cost), ("time", selected.batch_minutes)):
                self.metric_values[key].set(self._number(value, 1 if key != "cost" else 2))
            available = f" / {s.available_minutes:,.0f} available min" if s.available_minutes is not None else ""
            self.feasibility.configure(text=f"Feasible   {selected.tool_sets} allocated edges/sets, {selected.tool_changes} changes{available}", fg=TEAL)
            if not base.feasible:
                self.feasibility.configure(text=self.feasibility.cget("text") + "\nBaseline infeasible: " + "; ".join(base.violations))
        else:
            for value in self.metric_values.values():
                value.set("—")
            self.feasibility.configure(text="No feasible operating point on the configured speed grid. Review demand and machine limits.", fg=RED)
        rows = (
            ("Cutting speed (m/min)", "speed_m_min", 1),
            ("Spindle speed (rpm)", "spindle_rpm", 0),
            ("Cutting time (min/part)", "cut_minutes", 3),
            (f"Machine cost ({s.currency}/part)", "machine_cost_per_part", 2),
            (f"Tooling cost ({s.currency}/part)", "tooling_cost_per_part", 2),
            (f"Other cost ({s.currency}/part)", "other_cost_per_part", 2),
            (f"Total unit cost ({s.currency}/part)", "unit_cost", 2),
        )
        for label, attr, digits in rows:
            self.comparison.insert("", "end", values=(label, self._number(getattr(base, attr), digits),
                                                       self._number(getattr(selected, attr), digits) if selected else "—"))
        for index, row in enumerate(result.trace):
            event = row.get("event", row.get("action", "step"))
            details = ", ".join(f"{key}: {value}" for key, value in row.items() if key not in ("event", "action"))
            self.trace_tree.insert("", "end", values=(f"{index + 1}  {event}", details))
        self.plot_hint.set("Teal: feasible cost. Gray: infeasible cost. Dashed: baseline. Solid marker: selected speed. Hover for details.")
        self.status.set(f"{result.message}  {len(result.evaluations):,} search evaluations on {result.grid_size:,} grid points.")
        if not base.feasible:
            self.status.set(self.status.get() + "  Baseline infeasible: " + "; ".join(base.violations))
        self._draw_chart()

    def _draw_chart(self) -> None:
        if not hasattr(self, "chart"):
            return
        canvas = self.chart
        canvas.delete("all")
        self._plot_hover = []
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if width < 150 or height < 100:
            return
        if self.result is None or not self._plot_samples:
            canvas.create_text(width / 2, height / 2, text="Cost and tool-life curves appear after optimization.",
                               fill=MUTED, font=("Segoe UI", 11))
            return
        s = self.result.scenario
        left, right, top, bottom = 70, width - 22, 30, height - 35
        usable = bottom - top - 40
        split = top + usable * 0.64
        regions = [(top, split, "unit_cost", f"Unit cost ({s.currency}/part)"),
                   (split + 42, bottom, "predicted_life_minutes", "Tool life (cutting min)")]
        span = max(s.speed_max - s.speed_min, 1e-12)
        xpos = lambda value: left + (value - s.speed_min) / span * (right - left)
        for ytop, ybottom, attr, label in regions:
            values = [getattr(p, attr) for p in self._plot_samples if math.isfinite(getattr(p, attr))]
            if not values:
                continue
            low, high = min(values), max(values)
            if high == low:
                high = low + max(1.0, abs(low) * 0.1)
            padding = (high - low) * .08
            low, high = max(0.0, low - padding), high + padding
            ypos = lambda value: ybottom - (value - low) / (high - low) * (ybottom - ytop)
            canvas.create_text(left, ytop - 15, text=label, anchor="w", fill=NAVY,
                               font=("Segoe UI", 9, "bold"))
            for i in range(4):
                value = low + (high - low) * i / 3
                y = ypos(value)
                canvas.create_line(left, y, right, y, fill="#e4eaee")
                canvas.create_text(left - 9, y, text=f"{value:,.1f}", anchor="e", fill=MUTED, font=("Segoe UI", 8))
            previous = None
            for sample in self._plot_samples:
                value = getattr(sample, attr)
                if not math.isfinite(value):
                    previous = None
                    continue
                x, y = xpos(sample.speed_m_min), ypos(value)
                if previous:
                    px, py, pf = previous
                    canvas.create_line(px, py, x, y, fill=TEAL if sample.feasible and pf else "#bbc4cc", width=2)
                previous = (x, y, sample.feasible)
                if attr == "unit_cost":
                    self._plot_hover.append((x, sample))
            base = self.result.baseline
            if s.speed_min <= base.speed_m_min <= s.speed_max:
                x = xpos(base.speed_m_min)
                canvas.create_line(x, ytop, x, ybottom, fill=AMBER, dash=(4, 4))
            best = self.result.best
            if best is not None and math.isfinite(getattr(best, attr)):
                x, y = xpos(best.speed_m_min), ypos(getattr(best, attr))
                canvas.create_line(x, ytop, x, ybottom, fill=TEAL, dash=(2, 3))
                canvas.create_oval(x - 4, y - 4, x + 4, y + 4, fill=TEAL, outline=WHITE, width=2)
        for i in range(6):
            speed = s.speed_min + (s.speed_max - s.speed_min) * i / 5
            x = xpos(speed)
            canvas.create_text(x, height - 21, text=f"{speed:,.0f}", fill=MUTED, font=("Segoe UI", 8))
        canvas.create_text((left + right) / 2, height - 5, text="Cutting speed (m/min)", fill=MUTED, font=("Segoe UI", 8))

    def _hover_chart(self, event: Any) -> None:
        if not self._plot_hover:
            return
        _, sample = min(self._plot_hover, key=lambda item: abs(item[0] - event.x))
        status = "feasible" if sample.feasible else "; ".join(sample.violations)
        self.plot_hint.set(f"{sample.speed_m_min:.2f} m/min   Cost {self._number(sample.unit_cost)}   "
                           f"Life {self._number(sample.predicted_life_minutes)} min   {status}")

    def _save(self) -> None:
        try:
            scenario = self._scenario()
            path = filedialog.asksaveasfilename(parent=self, title="Save scenario", defaultextension=".json",
                                                filetypes=[("Scenario JSON", "*.json")])
            if path:
                save_scenario(path, scenario)
                self.status.set("Scenario saved.")
        except (ValueError, OSError, TypeError) as error:
            messagebox.showerror("Save scenario", str(error), parent=self)

    def _material_reference(self) -> None:
        path = Path(__file__).resolve().parent.parent / "references" / "material_reference.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            messagebox.showerror("Material references", str(error), parent=self)
            return
        window = tk.Toplevel(self)
        window.title("Metal reference data")
        window.geometry("940x400")
        window.configure(bg=WHITE)
        ttk.Label(window, text="Nominal material conditions", font=("Segoe UI", 15, "bold")).pack(anchor="w", padx=18, pady=(18, 8))
        ttk.Label(window, text=data["meaning"], style="Note.TLabel", wraplength=900).pack(fill="x", padx=18, pady=(0, 12))
        columns = ("name", "code", "hardness", "kc1_n_mm2", "mc")
        table = ttk.Treeview(window, columns=columns, show="headings", height=6)
        for key, title, width in zip(columns, ("Material condition", "MC code", "Hardness", "kc1 (N/mm²)", "mc"), (350, 130, 100, 130, 70)):
            table.heading(key, text=title)
            table.column(key, width=width, stretch=key == "name")
        for i, row in enumerate(data["materials"]):
            table.insert("", "end", iid=str(i), values=[row[key] for key in columns])
        table.pack(fill="x", padx=18)
        actions = ttk.Frame(window, style="White.TFrame", padding=18)
        actions.pack(fill="x")

        def use_metadata() -> None:
            selected = table.selection()
            if selected:
                row = data["materials"][int(selected[0])]
                self.vars["material_name"].set(row["name"] + " (" + row["code"] + ")")
                self.vars["hardness_label"].set(row["hardness"] + " (nominal reference)")
                self.status.set("Material metadata copied. Enter matching effective kc and tool-life calibration.")
                window.destroy()
        ttk.Button(actions, text="Use selected material metadata", command=use_metadata).pack(side="left")
        ttk.Button(actions, text="Open source", command=lambda: webbrowser.open(data["source"])).pack(side="left", padx=8)
        ttk.Button(actions, text="Close", command=window.destroy).pack(side="right")

    def _open(self) -> None:
        if self._busy:
            return
        path = filedialog.askopenfilename(parent=self, title="Open scenario", filetypes=[("Scenario JSON", "*.json")])
        if not path:
            return
        try:
            scenario = load_scenario(path)
            self._mode_cache[self.current_mode] = {key: var.get() for key, var in self.vars.items()}
            self._fill(scenario)
            self._invalidate("Scenario opened. Run optimization.")
        except (ValueError, OSError, TypeError) as error:
            messagebox.showerror("Open scenario", str(error), parent=self)

    def _export(self, kind: str) -> None:
        if self.result is None:
            return
        path = filedialog.asksaveasfilename(parent=self, title=f"Export {kind.upper()} result", defaultextension=f".{kind}",
                                            filetypes=[(kind.upper(), f"*.{kind}")])
        if not path:
            return
        try:
            (export_result_json if kind == "json" else export_result_csv)(path, self.result)
            self.status.set(f"{kind.upper()} result exported.")
        except (ValueError, OSError, TypeError) as error:
            messagebox.showerror("Export result", str(error), parent=self)


def main() -> None:
    app = OptimizerApp()
    app.mainloop()
