# Submission Gap Closure Report

Дата: 2026-09-27.

## Цель

Зафиксировать, что уже подтверждено для хакатонной сдачи, и отделить это от
оставшихся разрывов: дальность, обобщаемость и real-time throughput.

## Evidence

- `README.md`, `SOLUTION.md`, `docs/README_noise_classifier.md`.
- `artefacts/current_model_validation/evaluation_summary.json`.
- `artefacts/current_model_validation/direct_player_http_timing_new_data_1050_1150.json`.
- `artefacts/current_model_validation/ros2_parity_timing.json`.
- `artefacts/stage_5/direct_player/parity.json`.
- `models/noise_classifier_candidate_baseline_v2.json`.
- `docs/reports/submission/headless_ros2_smoke_20260927.md`.

## Текущий подтверждённый срез

Сдачный runtime — `baseline_v3`, а не отдельная ML-модель. Он использует
geometry-first gate, boundary/warning и temporal model-assist; `candidate_baseline_v2`
остаётся встроенным score assist-ветки.

Свежая runtime-сводка `baseline_v3`:

| Проверка | Результат |
|---|---|
| Real frame runtime | `TP=51`, `FN=1`, `FP alarm=50`, `frames=13759`, `UNKNOWN=13658` |
| `cloud_with_fake_obj` event windows | `6/6` positive events hit, `0` false-positive boundary events |
| Direct compute timing | processing p95 `52.25` ms on `new_data` frames `1050..1150` |
| Direct HTTP timing | wall p95 `133.16` ms, p99 `1932.03` ms |
| ROS2 parity/timing | `PASS`, `201` cases, wall `137.557` s |

## Разрывы к критериям

| Критерий | Статус | Что нужно доделать |
|---|---|---|
| 8.1 Работоспособность | частично | Разобрать 50 `FP alarm` и один initial FN текущего `baseline_v3`. |
| 8.2 Дальность | не закрыт | Измерить first/stable detection distance по `cloud_with_fake_obj` и доступным positive windows; `80 м` оставить только параметром envelope. |
| 8.3 Скорость | частично | Сделать полный ROS2 replay с counts, drops, queue starvation, p50/p95/p99 latency, CPU/RAM и длительностью. |
| 8.4 Обобщаемость | не доказана | Зафиксировать held-out split и не донастраивать по test; `doubleT_obstacle` считать development-positive, synthetic — screening evidence. |
| 8.6 Запуск | средне | Использовать `scripts/run_submission_ros2_demo.ps1` как единую точку старта headless ROS2 demo. |

## Выполненные команды

В рамках этого отчёта выполнено read-only сравнение документации и артефактов:

```powershell
rg -n "candidate_baseline_v2|baseline_v3|TP=51|55.568|52.25|real-time" README.md SOLUTION.md docs
Get-Content -Raw artefacts\current_model_validation\evaluation_summary.json
Get-Content -Raw artefacts\current_model_validation\direct_player_http_timing_new_data_1050_1150.json
Get-Content -Raw artefacts\current_model_validation\ros2_parity_timing.json
```

## Уровень валидации

Документальный и артефактный evidence review: L1 для описания текущего состояния.
Это не новый runtime-прогон и не доказательство production real-time.

## Следующий минимальный тест

Запустить headless ROS2 demo через:

```powershell
.\scripts\run_submission_ros2_demo.ps1 -BuildImage -StopExisting -Play
```

После этого сохранить stdout/stderr replay и отдельно посчитать количество
полученных JSON-сообщений, задержки, dropped/starved признаки и ресурсы процесса.
