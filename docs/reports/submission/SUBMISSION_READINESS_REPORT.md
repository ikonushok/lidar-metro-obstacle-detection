# Submission Gap Closure Report

Дата: 2026-09-27. Обновлено по speed evidence: 2026-09-28.

## Цель

Зафиксировать, что уже подтверждено для хакатонной сдачи, и отделить это от
оставшихся разрывов: дальность, обобщаемость и real-time throughput.

## Evidence

- `README.md`, `SOLUTION.md`, `docs/METHODOLOGY.md` — публичное описание запуска, решения и метода.
- `artefacts/current_model_validation/evaluation_summary.json` — зафиксированная runtime-сводка `baseline_v3`.
- `artefacts/current_model_validation/direct_player_http_timing_new_data_1050_1150.json` — direct HTTP/compute timing на интервале `new_data`.
- `artefacts/current_model_validation/ros2_parity_timing.json` — parity/timing direct и ROS2 на одном входе.
- `artefacts/current_model_validation/headless_ros2_cpp_performance_rate_1p0_summary_diagnostics_summary.json` — headless ROS2/C++ timing без плеера на `doubleT_obstacle` в compact diagnostics.
- `artefacts/current_model_validation/detection_distance_summary.json` — first warning / first public detection distance по `doubleT_obstacle` и `cloud_with_fake_obj` positive windows.
- `artefacts/stage_5/direct_player/parity.json` — дополнительный артефакт сверки direct player.
- `models/baseline_v3_runtime_policy.json` — версия передаваемой runtime-policy.
- `docs/reports/submission/ROS2_HEADLESS_DEMO_VERIFICATION.md` — журнал headless ROS2 smoke-проверки.
- `docs/reports/submission/HEADLESS_ROS2_CPP_PERFORMANCE.md` — журнал headless ROS2/C++ performance-проверки.
- `docs/reports/submission/DETECTION_DISTANCE_REPORT.md` — журнал измерения расстояний обнаружения на доступных positive windows.

## Текущий подтверждённый срез

Runtime для сдачи — `baseline_v3`, а не отдельная ML-модель. Он использует
geometry-first gate, boundary/warning и temporal model-assist; слабый score
встроен внутрь `baseline_v3`.

Свежая runtime-сводка `baseline_v3`:

| Проверка | Результат |
|---|---|
| Real frame runtime | `TP=51`, `FN=1`, `FP alarm=50`, `frames=13759`, `UNKNOWN=13658` |
| `cloud_with_fake_obj` event windows | `6/6` positive events hit, `0` false-positive boundary events |
| Direct compute timing | processing p95 `52.25` ms on `new_data` frames `1050..1150` |
| Direct HTTP timing | wall p95 `133.16` ms, p99 `1932.03` ms |
| ROS2 parity/timing | `PASS`, `201` cases, wall `137.557` s |
| Headless ROS2 C++ timing without player | compact diagnostics: `187/201` JSON, processing p95 `71.78` ms, `Message queue starved` |
| Detection distance on positive windows | `doubleT_obstacle`: first public detection `55.580` m; `cloud_with_fake_obj` user-visible windows: first public detection from f137 / `68.069` m |

## Разрывы к критериям

| Критерий | Статус | Что нужно доделать |
|---|---|---|
| 8.1 Работоспособность | частично | Разобрать 50 `FP alarm` и один initial FN текущего `baseline_v3`. |
| 8.2 Дальность | закрыт для доступных positive windows; не production-distance | Измерено по `doubleT_obstacle` и пользовательским visible windows `cloud_with_fake_obj`: first public detection `55.580` м на real development interval; на fake-object окнах first public detection начинается с f137 / `68.069` м. `80 м` остаётся только параметром envelope, расстояние считается от source origin, не от носа поезда. |
| 8.3 Скорость | частично, detector compute закрыт на development bag; full replay не закрыт | Headless ROS2/C++ замер без плеера в compact diagnostics показал p95 `71.78` ms и max `74.96` ms, то есть detector compute укладывается в ориентир `100` ms для `10 Hz`. Но локальный replay дал `187/201` JSON и `Message queue starved`; следующий шаг — повторить на целевом Linux/Humble стенде. |
| 8.4 Обобщаемость | не доказана | Зафиксировать held-out split и не донастраивать по test; `doubleT_obstacle` считать development-positive, synthetic — screening evidence. |
| 8.6 Запуск | средне | Использовать `scripts/run_submission_ros2_demo.ps1` как единую точку старта headless ROS2 demo. |

### Формулировка обобщаемости для сдачи

Для отчёта и презентации текущие результаты формулируются так:

> Метрики `baseline_v3` посчитаны на доступных replay-источниках и служат
> воспроизводимым срезом текущего прототипа. `doubleT_obstacle` считается
> development-positive сценой, `cloud_with_fake_obj` — screening/working
> event-window evidence, а собственные synthetic-пробы не считаются скрытым
> независимым test set. Независимый held-out test организаторов заранее не
> заявляется.

Эта формулировка нужна, чтобы не завышать claim по обобщаемости: доступные
positive-сцены полезны для проверки и демонстрации, но не доказывают качество
на неизвестном наборе жюри.

## Хакатонная актуальность

Ниже только пункты, которые могут стоить баллов при проверке хакатонной версии.
Production-долг вроде полной калибровки монтажа, `/tf`, IMU, карты,
сертификации и safety case остаётся ограничением MVP, но не является
предусловием отправки текущего решения.

| Приоритет | Пункт | Что можно закрыть документацией | Что требует отдельного запуска или исследования |
|---|---|---|---|
| P0 | Доступ и комплект материалов | Перечислить в `SUBMISSION_CHECKLIST.md` все ссылки/файлы: repo, docs, presentation, prototype/screencast, extra materials. | Открытие репозитория и проверка внешних ссылок из приватного окна выполняются владельцем перед отправкой. |
| P0 | Чистый пакет сдачи | Описать обязательный gate и исключённые локальные данные/артефакты. | Запуск `scripts/check_submission_package.py --require-clean` на финальном commit. |
| P1 | Воспроизводимый запуск | Указать `scripts/run_submission_ros2_demo.ps1` как основной headless route и оставить player как демонстрационный путь. | Чистая сборка и replay на финальном commit, если нужно обновить evidence. |
| P1 | Работоспособность `baseline_v3` | Честно зафиксировать текущие `TP/FN/FP/UNKNOWN` и смысл FP/FN. | Разбор 50 `FP alarm` и initial FN требует анализа результатов/данных. |
| P1 | Обобщаемость | Зафиксировать split-интерпретацию: `doubleT_obstacle` — development-positive, `cloud_with_fake_obj` — screening/working event windows, synthetic — не скрытый test. | Новый независимый held-out test или переразметка требуют отдельной работы. |
| P2 | Презентация и demo evidence | Сослаться на готовые PPTX/кадры/видео и ограничения. | Новый скринкаст полного запуска требует отдельной записи. |

## Выполненные команды

В рамках этого отчёта выполнено read-only сравнение документации и артефактов:

```powershell
rg -n "baseline_v3|TP=51|55.568|52.25|real-time" README.md SOLUTION.md docs
Get-Content -Raw artefacts\current_model_validation\evaluation_summary.json
Get-Content -Raw artefacts\current_model_validation\direct_player_http_timing_new_data_1050_1150.json
Get-Content -Raw artefacts\current_model_validation\ros2_parity_timing.json
```

Обновление 2026-09-28 добавило headless ROS2/C++ performance-прогон без плеера:

```powershell
.\scripts\run_submission_ros2_demo.ps1 -BuildImage -StopExisting -Rate 1.0 -ReadAheadQueueSize 20 -DiagnosticsDetail summary
python .\scripts\measure_headless_ros2_cpp_performance.py `
  --rate 1.0 --read-ahead-queue-size 20 --expected-messages 201 `
  --collector-timeout-seconds 210 --output-stem headless_ros2_cpp_performance_rate_1p0_summary_diagnostics
```

## Уровень валидации

Документальный и артефактный evidence review: L1 для общего описания текущего
состояния. Headless ROS2/C++ speed evidence: L1/L3 для одного development bag.
Detector compute укладывается в `10 Hz`-ориентир на этом bag, но это не
доказательство полного production real-time replay.

## Следующий минимальный тест

Повторить compact diagnostics headless replay на целевом Linux/Humble стенде с
counts, drops, queue starvation, p50/p95/p99 latency, CPU/RAM и длительностью.
