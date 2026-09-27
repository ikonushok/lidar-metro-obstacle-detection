# Stage 5 — player arc mode cleanup

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Датированное изменение доступных режимов: tangent/arc_limited в player; arc_clamped оставлен в низкоуровневых C++/ROS экспериментах.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

- Date: 2026-09-23.
- Mode: patch.
- Goal: remove the misleading `arc_clamped` choice from the CPU player surfaces unless it can preserve `doubleT_obstacle` frames 13--64.
- Non-goals: no geometry, margin, model, TF, timestamp, ROS schema, QoS, C++ core or trained-noise-model changes.
- Evidence inspected: `agents/context_router.md`, `agents/lidar_obstacle_pipeline.md`, `scripts/run_stage_2_cpu_player.ps1`, `scripts/serve_stage_2_cpu_catalog.py`, `scripts/measure_cpu_catalog_window.py`, `scripts/cpu_catalog_runtime.py`, `tests/test_run_stage_2_cpu_player.py`, `docs/stages/stage_5/stage_5_arc_clamped_extension.md`.
- Prior evidence used: `stage_5_arc_clamped_extension.md` records `tangent + model_v1` preserving `52/52` frames in the known 13--64 interval, while checked `arc_clamped` configurations preserve `1/52` or `0/52`, and long-horizon checks miss frames 13 and 64.
- Change: `arc_clamped` is removed from player launcher and HTTP catalog/measurement argument choices. Low-level C++ and ROS paths keep it for explicit calibration experiments.
- Protected contracts: `UNKNOWN` is not treated as `CLEAR`; default remains `tangent`; safety decision remains candidate-only.
- Commands run:
  - `.\.venv\Scripts\python.exe -m unittest tests.test_run_stage_2_cpu_player tests.test_cpu_catalog_runtime_source_frame` -- PASS, 11 tests.
  - `.\.venv\Scripts\python.exe -c "import py_compile; [py_compile.compile(path, doraise=True) for path in ['scripts/serve_stage_2_cpu_catalog.py','scripts/measure_cpu_catalog_window.py','scripts/cpu_catalog_runtime.py']]"` -- PASS.
  - `rg -n "ValidateSet\('tangent', 'arc_limited'|choices=\('tangent', 'arc_limited'\)|arc_clamped" ...` -- confirmed player choices are `tangent`/`arc_limited`; `arc_clamped` remains only in docs/report text for this cleanup scope.
- Validation achieved: L1 static/unit contract for player mode availability. Runtime replay not rerun because geometry/model behavior was not changed.
- Residual risk: `arc_limited` remains selectable as experimental non-default; it still needs split-based calibration before any quality claim.

## Final player decision

- Keep `tangent + model_v1` as the only user-facing player/demo configuration.
- Do not expose `arc_clamped`: subsequent `doubleT_obstacle`, `roundT_doubleT`, and `roundT_pressureGate_roundT` diagnostics showed no runtime benefit over `tangent + model_v1`.
