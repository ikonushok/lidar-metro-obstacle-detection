# Stage 5 — arc_clamped forward extension

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Эксперимент/справка вне запуска direct_cpp+tangent+model_v1. Включение требует отдельной проверки эффекта и регрессии; результаты не меняют runtime default.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

## Задача

- Goal: добавить безопасный режим продления кривой оси `arc_clamped` для CPU-плеера.
- Наблюдаемая проблема: `arc_limited` на кадрах `roundT_pressureGate_roundT` может переоценивать кривизну по шумным последним rail-pairs и уводить габарит в слишком сильный поворот.
- Non-goals: не менять модель шума, габарит поезда, safety margin, разметку и правила классификации препятствий.
- Source of truth: текущий код C++/Python/PowerShell, screenshots пользователя, JSON-диагностика плеера.
- Этап: stage 5 / C++ CPU viewer integration.
- Целевое окружение: Ubuntu 22.04 + ROS 2 Humble + Docker.
- Входные данные: `roundT_pressureGate_roundT`, кадры около `227–246`; режим direct CPU stream.
- Working frame: source XYZ, ось строится в source coordinates по detected rail pairs; TF не используется.
- Allowed files: C++ core/CLI/node, CPU runtime/server/launcher, узкие tests, этот отчёт.
- Protected contracts: `UNKNOWN` не становится `CLEAR`; старые режимы `tangent` и `arc_limited` сохраняются; модель `model_v1` не меняется.
- Safety reviewer: нужен, потому что меняется продление оси/габарита.
- Validation target: L1-L3 для реализации и smoke-проверки интерфейса; качество на всех датасетах не заявляется.
- Acceptance criteria:
  - `arc_clamped` доступен из launcher;
  - дуга оценивается по сглаженному окну `ArcFitWindowPairs`, а не только по последним 3 rail-pairs;
  - неприемлемая дуга оставляет только observed geometry с явным статусом, без tangent fallback;
  - угол дуги ограничивается `MaxArcTurnDeg`;
  - JSON содержит параметры и статус;
  - не добавлять смешивание геометрий: выбранный `ForwardExtensionMethod` должен сам определять габарит;
  - для `doubleT_obstacle` отдельно проверять, что нет ложных срабатываний вне известного интервала помехи;
  - C++ Docker build проходит.

## Отчёт о завершении

- Что изменено: добавлен `arc_clamped = smoothed arc fit over last N rail-pairs + min radius guard + max turn clamp`.
- Evidence inspected: `curve_envelope_core.*`, `curve_pipeline_stream_cli.cpp`, `curve_envelope_node.cpp`, CPU runtime/server/launcher, связанные tests.
- Commands run:
  - `python -m unittest tests.test_cpu_catalog_runtime_source_frame tests.test_run_stage_2_cpu_player` in `python:3.11-slim` — OK.
  - `node .\tests\test_cpu_viewer_distance_and_noise.cjs` — 11/11 pass.
  - `docker build -t lidar-arc-clamped-check .` — OK after fixing ROS node branch order.
  - `g++ -std=c++17 -Isrc/cpp tests/test_curve_envelope_core.cpp src/cpp/curve_envelope_core.cpp -o /tmp/test_curve_envelope_core && /tmp/test_curve_envelope_core` in Docker — OK.
  - `curve_pipeline_stream_cli 2 --arc-clamped 10 150 8 --use-model-filter` early-UNKNOWN smoke — OK, JSON contains `arc_clamped`, clamp params, `noise_filter_mode=model_v1`.
  - Direct runtime on `roundT_pressureGate_roundT` frame `246`, `arc_clamped`, horizon `10`, radius `150`, turn `8` — OK; returned `ARC_CLAMPED_FALLBACK_TANGENT` because estimated radius was about `74.06 m`.
  - Initial smoothing update added a `tangent` guard for `arc_clamped`; this was removed because it mixed two rail extension algorithms and could reintroduce false positives from `tangent`.
  - After removing the guard, full direct runtime on `doubleT_obstacle`, `tangent`, `model_v1` — OK; `201` frames, known interval `13–64` has `52/52` obstacle hits, false hits outside the known interval: `0`.
  - After removing the guard, full direct runtime on `doubleT_obstacle`, `arc_clamped`, horizon `5`, radius `60`, turn `4`, window `7` — checked; false hits outside the known interval: `0`, but known interval has only `1/52` hits.
  - After removing the guard, full direct runtime on `doubleT_obstacle`, `arc_clamped`, horizon `10`, radius `60`, turn `8`, window `5` — checked; known interval has `0/52` hits, false hits outside the known interval: `2` (`145`, `185`).
  - After smoothing update, direct runtime on `roundT_pressureGate_roundT` frames `247/248/251`, same config — OK; frame `247` applied smoothed arc with radius about `93.47 m`, frame `248` fell back to tangent at radius about `55.17 m`, frame `251` applied smoothed arc with radius about `334.03 m`.
  - `py_compile` for changed Python files — OK.
  - `git diff --check` — OK, CRLF warnings only.
- Validation level achieved: L3 for build/interface and targeted `doubleT_obstacle` replay; not a quality claim for all datasets.
- Что не проверено: полный прогон всех датасетов и подбор оптимальных параметров на отдельном calibration split.
- Известные FP/FN или safety-риски: на `doubleT_obstacle` режим `arc_clamped` параметрами из текущей проверки не даёт одновременно `0` FP и сохранение известной помехи; для этого датасета рабочий режим — `tangent`.
- Следующий минимальный тест: сравнить `tangent`, `arc_limited`, `arc_clamped` на кадрах `roundT_pressureGate_roundT` 227–246 и затем сделать split-based calibration без смешивания алгоритмов.
- Residual risk: при неверных параметрах дуга может быть слишком короткой или слишком прямой; это безопаснее, чем неконтролируемое закручивание, но может увеличить `UNKNOWN`/пропуски дальних пересечений.

## Arc-only update — 2026-09-23

- Runtime status: `tangent` remains the only working default. `arc_clamped` is an experimental geometry-calibration mode and must not be used in production while it misses the known `doubleT_obstacle` frames 13 and 64.
- `ARC_CLAMPED_REJECTED` заменяет внутренний tangent fallback: при недостаточных данных, невалидном fit или радиусе ниже порога synthetic pair не создаётся.
- C++ regression: rejected arc оставляет только observed pairs; gentle radius-300 m arc сохраняет gauge и достигает 80 м.
- Docker build `lidar-arc-verified-check` — OK.
- Direct runtime: `roundT_pressureGate_roundT`, frames `132/136/229`, horizon `53`, radius minimum `100`, turn maximum `15`, window `7` — applied radii `271.90/327.05/232.21` м; turns `11.17/9.29/13.08` градусов; endpoint `80` м.
- Same config on `doubleT_obstacle` frames `13/64/145/185`: all false. Known obstacle is missed at 13 and 64; `arc_clamped` must not replace default `tangent`.
- Safety verdict: `PASS_WITH_RISKS`; a rejected curve covers no unobserved path and retains candidate-only `UNKNOWN` system status. Full post-change replay remains outstanding.

## Player availability correction - 2026-09-23

- `arc_clamped` removed from the CPU player launcher and HTTP catalog argparse choices because checked configurations do not preserve the known `doubleT_obstacle` interval 13--64.
- C++ core, ROS node parameter handling and low-level smoke tooling still keep `arc_clamped` for explicit geometry-calibration experiments outside the player mode list.
- Working player modes are now `tangent` and `arc_limited`; production/demo default remains `tangent + model_v1`.
