# Committed requirements

Requirement baseline REQ-TOOL-LIFE-001, revision 1, approved 2026-10-06.
Human authorization: the user replied YES to A-001 through A-005 in this chat.

| ID | Committed behavior | Acceptance evidence |
|---|---|---|
| R01 | Separate turning and milling operation scenarios, fixed machining conditions | Hand-calculated RPM, feed, time, power vectors for both modes |
| R02 | Independent Taylor curves T=Tref*(vref/v)^(1/b), with labeled calibration origin | Reference-speed identity, decreasing life, independent profiles |
| R03 | Finite integer demand, fresh tooling, between-part changes, full allocated tool charges | One-part, exact-life, multi-set, and milling insert-cost vectors |
| R04 | Unit cost includes machine time, allocated tooling, other part and batch costs | Independent cost arithmetic and breakdown reconciliation |
| R05 | Enforce speed, RPM, axis feed, power, part-completing life, and optional batch-time limits | Constraint rejection and infeasible-domain checks |
| R06 | Deterministic multistart hill climbing on a bounded speed grid with decreasing steps | Repeatability, baseline preservation, small-domain exhaustive comparison |
| R07 | Python desktop UI with grouped inputs, comparisons, plots, save/load, JSON/CSV exports | GUI smoke tests, save/load round trip, export readback, rendered UI inspection |
| R08 | Separate business semantics from optimization search and UI | engine.py imports no UI/search modules; search.py invokes the business evaluator |
| R09 | Traceable requirements, fixed acceptance vectors, approval log, SHA-256 evidence | requirements/UEP/provenance linkage and recomputed digests |
| R10 | One editable marketing PowerPoint slide, no pricing | One-slide package, native editable text, rendered inspection, pricing audit |

## Approved assumptions

A-001 (MEDIUM): One turning or milling operation per scenario. Feed, depths,
geometry, tool, material, engagement and coolant remain fixed while speed varies.
Entered other production costs remain fixed across speed candidates.

A-002 (HIGH): Material-family metadata does not supply universal cutting speeds
or Taylor constants. Demo numbers are synthetic and labeled. Measured/supplier
profiles must identify matching conditions and calibration source. Life denotes
accumulated cutter-in-cut clock minutes at those fixed conditions.

A-003 (HIGH): Begin with a fresh edge/set. Initial installation belongs to setup.
One edge/set must finish a part. Index between parts and charge every allocated
edge/set fully, with no residual-life credit. Indexable milling renews all physical
insert positions together; solid milling charges the whole cutter once per set.
Demand is integer batch quantity. Available minutes are allocated effective machine
minutes, not calendar time. Machine rate covers labor/overhead as entered.

A-004 (MEDIUM): Use bounded deterministic multistart hill climbing and report the
best feasible point found, without a global-optimum guarantee. Exhaustive searches
are independent test oracles. A complete feasibility-only fallback is permitted
when starts find no feasible point, to avoid falsely declaring a disconnected
feasible region impossible.

A-005 (LOW): Local Python desktop app, saved scenarios and exported results;
one editable PowerPoint marketing slide after software verification, no pricing.

## Numeric policy

Python binary64 calculations; reject nonfinite inputs. A bounded grid contains
at most 20,001 speeds including the upper endpoint. Display rounding never alters
calculations. Tool-capacity boundary tolerance is specified in the engine and
tested; it only absorbs floating-point roundoff. Reproducibility applies to input,
evaluations, selected result and iteration trace, excluding timestamps and paths.

## Evidence limits

Tests verify the declared mathematical model and software behavior. Demo outputs
do not establish measured tool life, sudden-fracture risk, surface quality,
collision-free toolpaths, or realized factory savings. This delivery does not claim
third-party AI-DES certification or authenticated expert identity signatures.
