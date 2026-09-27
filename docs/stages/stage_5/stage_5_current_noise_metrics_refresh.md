# Current noise metrics refresh

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Спецификация отдельной проверки метрик. Target/acceptance не являются выполненным результатом; новые числа требуют версии и исправной методики таймеров.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

- Дата: 2026-09-23.
- Режим: validation -> docs patch.
- Цель: пересчитать метрики `docs/README_noise_classifier.md` на текущем рабочем коде, а не переносить smoke-метрики коммита `4d5bb30`.
- Scope: полный offline-прогон семи источников по `scripts/evaluate_noise_classifier.py`; при доступности также текущий production-like/debug timing для окна `new_data`, как в README.
- Non-goals: переобучение `noise_classifier_doubleT_obstacle_v1`, изменение модели/порогов/геометрии, claims independent recall/real-time.
- Allowed files: `docs/README_noise_classifier.md`, этот отчёт, новые артефакты в `artefacts/stage_5/noise_model_eval_current/` и timing-подкаталогах.
- Evidence: текущий Docker build из рабочего дерева; JSON-результаты evaluator/benchmark; `git diff --check`.
- Контракты: `UNKNOWN` не считается `CLEAR`; отрицательный ответ модели не доказывает свободный путь; положительный интервал `doubleT_obstacle` 13-64 остаётся development-разметкой.
- Acceptance: таблицы README содержат пересчитанные current-code значения, явно связаны с текущим коммитом/working tree и не смешаны со старым `C++ модель v1` benchmark.
- Target validation: L4 для полноты frame-level offline-прогона доступных источников; L1 для качества модели на новых препятствиях.

## Результат

- Текущий baseline: `c91ed30195679457cf1a79c3ac667dcf6d5def23` (`docs: align current pipeline instructions and separate historical materials`) + незакоммиченный working tree.
- Docker build: `docker build -t lidar-mosmetro3d:noise-current .` — PASS, colcon собрал 1 пакет. Image digest: `sha256:c5d02f52aebcdb9c3c05638762477f5d1790f7a21d28204d0f0fe17ee7e09fde`.
- Full evaluator: `docker run --rm --mount "type=bind,source=$((Get-Location).Path),target=/workspace" -w /workspace -e PYTHONPATH=/workspace/scripts:/workspace/src lidar-mosmetro3d:noise-current python3 scripts/evaluate_noise_classifier.py --root /workspace --output /workspace/artefacts/stage_5/noise_model_eval_current` — PASS.
- Lean benchmark: `docker run --rm ... lidar-mosmetro3d:noise-current python3 scripts/benchmark_lean_noise_model.py --root /workspace --output /workspace/artefacts/stage_5/noise_model_lean_timing_current_new_data_5min` — PASS.

Full evaluator обработал 13 759/13 759 кадров семи источников: `UNKNOWN=193`. Legacy filter: TP/FN/FP/TN = `52/0/4797/8717`. Current model_v1: TP/FN/FP/TN = `52/0/457/13057`. Для `doubleT_obstacle` помеха на кадрах 13-64 найдена: `TP=52`, `FN=0`; `48/0` в таблице означает ложные тревоги вне положительного интервала для legacy/model.

Current lean benchmark на первых 5 минутах `new_data`: 3000 кадров, `UNKNOWN=29`, FP=129, TN=2842, p95 decision/common/model-filter = `266.3/192.8/72.9` мс.

README обновлён: `docs/README_noise_classifier.md` теперь связывает таблицы с current run и артефактами `artefacts/stage_5/noise_model_eval_current/*.json` и `artefacts/stage_5/noise_model_lean_timing_current_new_data_5min/new_data.json`; smoke-секция коммита `4d5bb30` убрана из основного сравнения, чтобы не смешивать интеграционную проверку с full evaluator.

Validation: L4 для полноты offline frame-level прогона доступных источников; L1 для качества модели на новых препятствиях, потому что независимого положительного проезда нет. Real-time/скорость по ТЗ не подтверждены: stream timing имеет известное ограничение методики и не заменяет ROS2 replay с очередью/drops на целевом стенде.

## Дополнение после фикса таймеров

Позднее в этой же дате B01 исправлен отдельно; см. [stage_5_stream_timing_fix.md](stage_5_stream_timing_fix.md). Frame-level counts из этого отчёта остаются актуальными для условной разметки, потому что логика фильтров не менялась. Timing `266.3/192.8/72.9` мс из image `noise-current` заменён новым lean benchmark после фикса: `118.5/47.9/73.8` мс на image `timing-fix`.
