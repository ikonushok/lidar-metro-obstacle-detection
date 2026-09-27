# Stage 5 — default rail search from 2 m and frame 23 diagnostic

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией. Команда явно передаёт 2 м; более поздний direct constructor имеет отдельный default 3 м, поэтому историческое «нигде нет 3» больше не обобщается на весь код.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

## Goal

Accept `rail_forward_min_m=2.0` as the default near rail-search boundary and diagnose the visible `doubleT_obstacle` frame 23 candidate shown in the CPU viewer.

## Scope

- Changed defaults only; no profile, margin, frame, TF, timestamp, envelope membership, tracking, TTC, background subtraction, or `CLEAR` decision changes.
- The algorithm remains candidate-only: `safety_decision_permitted=false`.
- The screenshot is treated as user guidance to inspect `doubleT_obstacle`, frame 23; it is not detector input.

## Changes

- Default `forward_min` changed from `3.0` to `2.0` in C++ rail config, ROS2 node parameter declaration, lazy CPU runtime, HTTP/measure launch paths, PowerShell launcher, smoke helper, and browser AutoRails config.
- The C++ envelope now extends the last observed rail pair forward along the final local tangent up to `rail_forward_max_m`. This makes the train volume continue ahead of the last confidently observed rail pair instead of stopping there.
- C++ JSON distinguishes observed and continued geometry with `observed_rail_pair_count`, `forward_extrapolated`, `observed_support_end_source_s_m`, `envelope_forward_end_source_s_m`, and per-pair `observed`.
- Regression checks now assert that the CPU player/runtime default is `2.0`.
- The UI lifecycle test was corrected to assert the successful auto-axis status from `axis-info`, where the current UI writes it.

## Frame 23 diagnostic

Evidence source: running CPU viewer API at `http://127.0.0.1:8100`, dataset `doubleT_obstacle`, frame `23`, with `rail_search_config.forward_min_m=2.0`.

Result before forward continuation:

- `status=OBSERVED_CORE_INTRUSION_CANDIDATE`
- `curve_axis_status=CURVE_AXIS_SUPPORTED`
- `rail_pair_count=16`
- supported pair stations: `3, 5, 7, ..., 31, 37 m`
- `core_count=1151`
- `margin_count=16502`
- `outside_reference_count=155476`
- `unknown_count=172977`
- nearest core candidate: source index `221831`, distance `3.788 m`, XYZ `[-0.915912, -3.342738, -1.528448]`

In the user-marked range around `27–31 m`:

- all displayed points in source-depth slice: `3697`
- core points: `27`, with `s=27.038–30.999 m`, `x=-2.165..-1.502`, `z=-1.887..-1.417`
- margin points: `550`, with `s=27.049–30.999 m`, `x=-2.718..1.154`, `z=-2.391..2.271`

Result after forward continuation, rebuilt Docker image and started clean viewer on port `8102`:

- `geometry_basis=ASSUMED_CURVE_RAIL_AXIS_WITH_FORWARD_TANGENT_EXTRAPOLATION_SOURCE_XYZ`
- `rail_pair_count=17`
- `observed_rail_pair_count=16`
- `forward_extrapolated=true`
- `observed_support_end_source_s_m=37.0`
- `envelope_forward_end_source_s_m=80.0`
- `core_count=1328`
- `margin_count=17850`
- `unknown_count=165044`

Depth slices after continuation:

| Source depth slice | Core | Margin |
|---:|---:|---:|
| `27–31 m` | 27 | 550 |
| `31–37 m` | 28 | 742 |
| `37–60 m` | 168 | 900 |
| `60–80 m` | 8 | 429 |

Interpretation: the train volume now continues forward to `80 m`; points past the observed end at `37 m` are classified against that continued volume and core points are emitted by C++ as red-layer source indices.

## Commands

- `.\.venv\Scripts\python.exe -m unittest tests.test_run_stage_2_cpu_player tests.test_cpu_catalog_runtime_source_frame` — PASS, `8/8`.
- `C:\Users\Ilya\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe --test tests\test_auto_rails.cjs` — PASS, `6/6`.
- `docker build -t lidar-mosmetro3d:stage-4-cpu-viewer -f Dockerfile .` — PASS, ROS 2 Humble package rebuilt.
- Docker C++ core regression: `g++ -std=c++17 -I/workspace/src/cpp /workspace/tests/test_curve_envelope_core.cpp /workspace/src/cpp/curve_envelope_core.cpp -o /tmp/test_curve_envelope_core && /tmp/test_curve_envelope_core` — PASS.
- Started `lidar-cpu-catalog-8102-development_candidate-fmin2`; `GET /api/cpu_sources/doubleT_obstacle/23.json` confirmed `forward_extrapolated=true` and `envelope_forward_end_source_s_m=80.0`.
- `rg -n 'forward_min = 3\.0|RailForwardMinM\s*=\s*3\.0|default=3\.0\)|"forwardMin": 3|rail_forward_min_m=3\.0' src scripts tests web -S` — no rail-search default hits; remaining `3.0` values are unrelated `fps`/motion-probe parameters.

## Safety Review

Verdict: `PASS_WITH_RISKS`.

- `UNKNOWN` is still not converted to `CLEAR`.
- `safety_decision_permitted=false` is unchanged.
- Extrapolated rail pair is explicit in JSON and used only to continue candidate detection, not to permit a `CLEAR` decision.
- Points inside core/margin are not suppressed.
- Risk: `fmin2` increases core/margin candidates and may include normal infrastructure; object-level diagnosis still needs manual/evaluator grouping before claims about a specific physical object.

## Validation Level

`L3` for this local Docker → C++ → HTTP frame-23 diagnostic and targeted regression checks. Full two-dataset recatalog after forward continuation remains not rerun.
