# Stream timing fix

Дата: 2026-09-23. Режим: bug fix -> validation. Этапы 5/6.

## Scope

- Цель: исправить B01 в `curve_pipeline_stream_cli`: обычный запуск не должен считать оба noise-фильтра, а `processing_ms` не должен повторно прибавлять уже учтённый filter time.
- Non-goals: переобучение модели, изменение threshold/geometry/labels, полный семиисточниковый quality rerun, ROS2/HTTP/UI full-path benchmark.
- Изменённые runtime files: `src/cpp/curve_pipeline_stream_cli.cpp`, `scripts/evaluate_noise_classifier.py`.
- Тестовый контракт: `tests/test_cpu_catalog_runtime_source_frame.py`.
- Документация: `docs/README_noise_classifier.md`, `docs/README_work_plan.md`, этот отчёт.

## Изменение

- Добавлен явный диагностический CLI-флаг `--compare-noise-filters`.
- Обычный stream CLI теперь считает только активный фильтр:
  - `legacy`, если нет `--use-model-filter` и нет `--lean-model-benchmark`;
  - `model_v1`, если есть `--use-model-filter` или `--lean-model-benchmark`.
- `scripts/evaluate_noise_classifier.py` теперь явно запускает `curve_pipeline_stream_cli 2.0 --compare-noise-filters`, потому что его задача — сравнение legacy/model_v1 на одном `CORE`.
- `common_processing_ms` измеряет общий путь до noise-фильтра; `processing_ms` складывает общий путь и активный фильтр, а в detailed JSON также wireframe. Lean benchmark больше не строит wireframe/debug arrays.
- Inactive filter timing/indices не публикуются в обычном JSON. В model mode остаются активные `reportable_core_source_indices` / `ignored_noise_source_indices`, которые использует viewer.

## Evidence

Команды:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_cpu_catalog_runtime_source_frame
docker build -t lidar-mosmetro3d:timing-fix .
docker run --rm --mount "type=bind,source=$((Get-Location).Path),target=/workspace" -w /workspace -e PYTHONPATH=/workspace/scripts:/workspace/src lidar-mosmetro3d:timing-fix python3 -c "... one-frame --use-model-filter smoke ..."
docker run --rm --mount "type=bind,source=$((Get-Location).Path),target=/workspace" -w /workspace -e PYTHONPATH=/workspace/scripts:/workspace/src lidar-mosmetro3d:timing-fix python3 scripts/evaluate_noise_classifier.py --root /workspace --output /workspace/artefacts/stage_5/timing_fix_eval_smoke --source doubleT_obstacle --first 13 --last 13
docker run --rm --mount "type=bind,source=$((Get-Location).Path),target=/workspace" -w /workspace -e PYTHONPATH=/workspace/scripts:/workspace/src lidar-mosmetro3d:timing-fix python3 scripts/benchmark_lean_noise_model.py --root /workspace --output /workspace/artefacts/stage_5/noise_model_lean_timing_timing_fix_new_data_5min
```

Результаты:

- Python static contract: 7 tests OK.
- Docker build: PASS, 1 C++ package. Image digest: `sha256:f37106bcef0e80920b1b2230abecb03fd30a55428fb1ca6db63775bfb30933ec`.
- One-frame ordinary model smoke, `doubleT_obstacle` frame 13: `noise_filter_mode=model_v1`, `model_noise_filter_status=APPLIED_ACTIVE`, `processing_ms=85.0`, `common_processing_ms=49.7`, `model_noise_filter_ms=35.3`; no `legacy_processing_ms` emitted.
- Diagnostic evaluator smoke, `doubleT_obstacle` frame 13: legacy/model both `TP=1`, `FN=0`, `UNKNOWN=0`; artifact `artefacts/stage_5/timing_fix_eval_smoke/doubleT_obstacle.json`.
- Current lean benchmark on first 5 minutes of `new_data`: 3000 frames, `UNKNOWN=29`, FP=129, TN=2842, p95 decision/common/model-filter = `118.5/47.9/73.8` ms; artifact `artefacts/stage_5/noise_model_lean_timing_timing_fix_new_data_5min/new_data.json`.

## Validation

Validation level: L1 for the timing fix and one-frame decision compatibility; L3 for successful Docker build + stream benchmark on a real 3000-frame window. Full seven-source quality counts were not rerun because decision logic did not change; the diagnostic evaluator smoke confirms both filters still identify the known positive frame. Full real-time compliance remains unproven without ROS2/HTTP/UI replay with queue/drops on the target environment.

Residual risk: `processing_ms` still excludes JSON serialization and external I/O. Detailed JSON mode includes wireframe construction by design; lean mode is the cleaner compute benchmark. Further optimization should profile component grouping/model filter internals, not the tiny decision tree comparison itself.

