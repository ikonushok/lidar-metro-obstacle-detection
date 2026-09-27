# Stage 5 — multi-hypothesis doubleT eval

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Эксперимент/справка вне запуска direct_cpp+tangent+model_v1. Включение требует отдельной проверки эффекта и регрессии; результаты не меняют runtime default. Обозначение L2 ниже исторически использовано для runtime smoke; по текущей шкале проекта L2 относится к instruction pack. Проверку трактовать только в явно описанном scope, не как новый уровень готовности.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

- Date: 2026-09-23.
- Mode: patch / offline validation.
- Goal: test a conservative diagnostic `tangent OR arc_clamped` candidate against the full `doubleT_obstacle` positive interval.
- Non-goals: no player mode, no runtime default, no C++ geometry, no model, no TF/deskew/profile/margin changes.
- Gate: `doubleT_obstacle` frames 13--64 must be `52/52` detected by the union and false positives outside the interval must remain `0`.
- Arc config under test: horizon 5 m, min radius 60 m, max turn 4 deg, fit window 7.
- Commands run:
  - `.\.venv\Scripts\python.exe -m unittest tests.test_evaluate_doublet_multi_hypothesis` -- PASS, 2 tests.
  - `.\.venv\Scripts\python.exe -c "import py_compile; [py_compile.compile(path, doraise=True) for path in ['scripts/evaluate_doublet_multi_hypothesis.py','tests/test_evaluate_doublet_multi_hypothesis.py']]"` -- PASS.
  - Docker full sequence: `evaluate_doublet_multi_hypothesis.py --root /workspace --output /workspace/artefacts/stage_5/multi_hypothesis_doublet_eval/summary.json` -- PASS, 201 frames.
- Results on `doubleT_obstacle`:
  - `tangent`: TP 52/52, FN 0, FP 0/149.
  - `arc_clamped`: TP 1/52, FN 51, FP 0/149.
  - `union = tangent OR arc_clamped`: TP 52/52, FN 0, FP 0/149.
  - Gate result: PASS for `doubleT_obstacle`.
- Artifacts: `artefacts/stage_5/multi_hypothesis_doublet_eval/summary.json` and `summary_frames.jsonl`.
- Validation achieved: L1 unit/compile plus L2 Docker full-sequence diagnostic on 201 frames.
- Residual risk: union passes by preserving tangent; this does not prove curved-path readiness. Next test must use curved-path windows such as `roundT_pressureGate_roundT` 227--251 and inspect FP growth.

## Curved-window diagnostic — roundT_pressureGate_roundT 227--251

- Command: Docker `evaluate_doublet_multi_hypothesis.py --source roundT_pressureGate_roundT --first 227 --last 251 --output /workspace/artefacts/stage_5/multi_hypothesis_roundT_pressureGate_227_251/summary.json` -- PASS, 25 frames.
- Result:
  - `tangent`: alarm frames 0/25.
  - `arc_clamped`: alarm frames 0/25.
  - `union = tangent OR arc_clamped`: alarm frames 0/25.
  - `arc_clamped` status: `ARC_CLAMPED_APPLIED` on 25/25 with 5.0 m horizon, but active model status stayed `NO_REPORTABLE_INTRUSION_NOISE_IGNORED`.
- Artifacts: `artefacts/stage_5/multi_hypothesis_roundT_pressureGate_227_251/summary.json` and `summary_frames.jsonl`.
- Interpretation: this window shows no added FP from the curve hypothesis, but it also gives no positive evidence that curve continuation improves obstacle detection. It remains a curved-path geometry diagnostic, not a detection-quality pass.

## Decision

- User-facing player/demo mode remains `tangent + model_v1`.
- `arc_clamped` is not restored to player choices: alone it misses `doubleT_obstacle`, and in `tangent OR arc_clamped` it did not improve FP/alarm counts on checked sources.
- `arc_clamped` may remain only as an offline geometry diagnostic until a future candidate both preserves `doubleT_obstacle` 13--64 and shows measurable benefit on curved-path validation.
