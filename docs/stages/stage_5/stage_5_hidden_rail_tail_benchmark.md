# Stage 5 — hidden rail-tail benchmark

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Эксперимент/справка вне запуска direct_cpp+tangent+model_v1. Включение требует отдельной проверки эффекта и регрессии; результаты не меняют runtime default. Обозначение L2 ниже исторически использовано для runtime smoke; по текущей шкале проекта L2 относится к instruction pack. Проверку трактовать только в явно описанном scope, не как новый уровень готовности.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

- Date: 2026-09-23.
- Mode: patch / diagnostic tooling.
- Goal: add a small offline benchmark that hides the last observed rail-pairs and compares geometric plus ML candidates for predicting that hidden tail.
- Non-goals: no runtime mode change, no obstacle metrics, no safety/CLEAR claim, no TF/deskew/profile/margin/model_v1 changes.
- Inputs: `curve_pipeline_stream_cli --arc-limited 0` to collect observed rail-pairs only; `ArchiveBagFrames` for bounded lazy source reads.
- Candidates: `tangent`, `arc_last3`, `arc_window_clamped`, and `ml_ridge_step`.
- ML scope: tiny ridge-linear next-step model over the last rail-pair kinematics; no sklearn/new dependency; trained only inside the benchmark split.
- Outputs: `summary.json` and `per_frame.jsonl` under a user-selected artifact directory.
- Commands run:
  - `.\.venv\Scripts\python.exe -m unittest tests.test_benchmark_hidden_rail_tail tests.test_run_stage_2_cpu_player` -- PASS, 9 tests.
  - `.\.venv\Scripts\python.exe -c "import py_compile; [py_compile.compile(path, doraise=True) for path in ['scripts/benchmark_hidden_rail_tail.py','tests/test_benchmark_hidden_rail_tail.py']]"` -- PASS.
  - Docker smoke: `benchmark_hidden_rail_tail.py --source doubleT_obstacle --first 13 --last 24 --hide-pairs 2 --train-fraction 0.5 --output /workspace/artefacts/stage_5/hidden_rail_tail_smoke` -- PASS.
  - Docker smoke v2 after adding saved prefix/prediction points: same command with `--output /workspace/artefacts/stage_5/hidden_rail_tail_smoke_v2` -- PASS.
  - `render_hidden_rail_tail_viz.py` generated an inline visualizer from smoke v2.
- Smoke result on `doubleT_obstacle` frames 13--24, hidden two tail pairs, eval frames 19--24:
  - `tangent`: mean XY error 2.938 m, p95 5.440 m, coverage 1.0.
  - `arc_last3`: mean XY error 0.649 m, p95 1.289 m, coverage 1.0.
  - `arc_window_clamped`: mean XY error 0.735 m, p95 1.244 m, coverage 1.0.
  - `ml_ridge_step`: mean XY error 0.698 m, p95 1.966 m, coverage 1.0.
- Artifacts: `artefacts/stage_5/hidden_rail_tail_smoke_v2/summary.json`, `per_frame.jsonl`, plus inline visualization source generated at `C:/Users/Ilya/.codex/visualizations/2026/09/23/01a0cc8c-55b2-7ec2-bf30-f7e446b795b9/hidden-rail-tail.html`.
- Validation achieved: L1 for helper/unit contracts plus L2 smoke for Docker/archive/C++ stream/output wiring on 12 development frames.
- Residual risk: smoke uses the same positive development interval and only checks rail-tail prediction, not obstacle preservation, FP/FN, held-out routes, or safety behavior.
