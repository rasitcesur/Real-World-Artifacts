# Tool Life Optimizer

A local Python desktop application for turning and milling economics. Choose a
cutting speed using deterministic multistart hill climbing, predict tool life,
and compare finite-batch unit costs against an entered baseline.

## Run

On this computer, double-click **Run_Optimizer.bat**. On another computer with
Python 3.10 or later and Tk support, run `python app.py`. The application uses
the Python standard library. No package install, service, account or network
connection is required to run it.

## Workflow

1. Choose Turning or Milling. Each mode retains its own input draft.
2. Enter batch demand and optionally allocated available machine minutes.
3. Define geometry, fixed feed/depths, tool conditions and machine limits.
4. Enter a compatible tool-life reference speed, reference life and Taylor
   exponent. Set calibration origin and record its source.
5. Enter your rate and tool cost. For indexable milling, tool cost means cost
   per usable insert edge; physical insert positions determine a full set's cost.
6. Select **Optimize**. Inspect the selected speed, life, cost breakdown,
   feasibility, comparison and recorded search steps.
7. Save a scenario or export the evaluated run as JSON/CSV.

The initially loaded scenarios contain **synthetic demonstration inputs**.
Switching the calibration label does not validate those inputs. Use measured or
supplier-specific curves and permitted machining ranges for your exact material,
hardness, tool, coolant, feed and engagement. Life is accumulated cutter-in-cut
clock time. Noncutting motion belongs in the noncutting-time input.

## Business model

With speed v in m/min, diameter D in mm, and exponent b:

    T(v) = Tref * (vref/v) ** (1/b)
    N(v) = 1000*v / (pi*D)

Turning:

    feed_rate = feed_per_revolution * N
    cutting_time = cutting_length * passes / feed_rate
    net_power = v * depth * feed_per_revolution * kc / 60000

Milling, at fixed effective diameter and engagement:

    feed_rate = feed_per_tooth * effective_teeth * N
    cutting_time = engaged_path_length * passes / feed_rate
    net_power = axial_depth * radial_width * feed_rate * kc / 60000000

`kc` is effective specific cutting force for the modeled conditions, in N/mm².
It differs from the material reference `kc1`; account for chip thickness and rake
when obtaining it. Motor demand equals net power divided by efficiency. Every
candidate must meet the RPM, axis feed and available motor-power limits. The
model rejects infeasible candidates rather than silently capping RPM.

Finite-batch accounting, with B parts:

    parts_per_tool = floor(predicted_life / cutting_time)
    tool_sets = ceil(B / parts_per_tool)
    changes = tool_sets - 1
    batch_minutes = setup + B*(noncutting + cutting_time) + changes*change_time
    unit_cost = (rate_per_hour/60*batch_minutes + tool_sets*set_cost
                 + other_batch_cost)/B + other_cost_per_part

One edge/set must complete a part. Fresh tooling installation belongs to setup.
Every allocated edge/set receives a full charge; there is no credit for residual
life after the batch. Turning charges a usable cutting edge. Indexable milling
charges all physical insert positions together. Solid milling charges one cutter
per set, independently of flute count.

The time limit means effective minutes allocated to this operation on one machine.
It is not elapsed calendar time, whole-factory capacity or a multi-operation route.
Fixed additional costs can account for other production costs but the optimizer
does not change them. Feed/depth, engagement and quality-qualified speed limits
remain fixed during the search.

## Search and validation

The search uses a speed grid, deterministic spaced starting points, and step
halving. It logs accepted moves and reports the best feasible point found. It
does not guarantee a continuous or global optimum. An exhaustive feasibility-only
fallback runs if the initial searches find no feasible point. Domain size is
bounded to 20,001 speeds. Use a finer grid to study speed sensitivity.

Run the acceptance suite:

    python -m unittest discover -s tests -v

The delivery's test report and artifact hashes are in `outputs`. These validate
the mathematical model and software behavior. They do not establish actual
shop-floor savings, measured wear, sudden fracture, dimensional quality or
collision-free machining. The delivery makes no third-party AI-DES certification
or authenticated expert identity signature claim.

## Architecture and approved baseline

`engine.py` contains business semantics. `search.py` contains hill climbing.
`ui.py` displays and edits scenarios. `persistence.py` stores versioned JSON and
exports finite JSON/CSV with SHA-256 run provenance. Display rounding does not
affect the calculations. Invalid edits invalidate the displayed run for export.

`requirements.md` and `unified_execution_plan.json` record committed R01-R10 and
the user's YES approval of A-001 through A-005 on 2026-10-06. `tests/golden_vectors.json`
holds fixed reference acceptance vectors.

## Research and sources

The Drive folder's **Material Selection.docx** connects machinability, tool wear,
power and cycle times to capacity. **Process selection.docx** frames demand,
cost, quality and flexibility as linked manufacturing decisions. The connector
text did not preserve embedded equations and some numerical table cells, so
no missing numeric value was imported as an empirical material constant.

- [Manufacturing Process Optimization folder](https://drive.google.com/drive/folders/186Bdzhf5zeGFonGZ9KiwWImWFUA3vejY)
- [AI-DES master specification](https://docs.google.com/document/d/1sNBGx9x8Nwf9CCBH_vnMCcHrLyjW479Gm1DdNwiArsc/edit)
- [Sandvik turning equations](https://www.sandvik.coromant.com/en-gb/knowledge/machining-formulas-definitions/general-turning-formulas-definitions)
- [Sandvik milling equations](https://www.sandvik.coromant.com/en-gb/knowledge/machining-formulas-definitions/milling-formulas-definitions)
- [Material classifications and reference force data](https://www.sandvik.coromant.com/en-gb/knowledge/materials/workpiece-materials)
- [Effective specific cutting force](https://www.sandvik.coromant.com/en-gb/knowledge/materials/specific-cutting-force)
- [Milling tool-life research, University of Tennessee](https://mtrc.utk.edu/wp-content/uploads/sites/45/2019/09/tool_life_bayesian_part_1.pdf)

Market research covered integrated CAD/CAM, process planning/simulation and tool
recommendation workflows. It informed grouped parameters, scenario comparison
and explicit feasibility in this focused application. It does not establish
market share or market size.

- [Siemens NX manufacturing planning](https://blogs.sw.siemens.com/designcenter/whats-new-june-2024-manufacturing-planning/)
- [Siemens Tecnomatix](https://www.siemens.com/en-us/products/tecnomatix/)
- [Autodesk Fusion Tool Library](https://help.autodesk.com/cloudhelp/ENU/Fusion-CAM/files/MFG-TOOL-LIBRARY-OVERVIEW.htm)
- [Mastercam machining solutions](https://www.mastercam.com/solutions/)
- [Sandvik CoroPlus ToolGuide workflow](https://videos.sandvik.coromant.com/search-for-a-tool-and-calculate)

The marketing deliverable is one editable PowerPoint slide in `outputs`, with
no pricing. Its feature claims describe this application.
