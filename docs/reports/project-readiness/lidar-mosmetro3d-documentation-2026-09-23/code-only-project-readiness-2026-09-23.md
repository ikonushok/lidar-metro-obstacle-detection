# Код и фактическая реализация — 2026-09-23

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Датированный аудит до редакции D0–D3; findings и рекомендации описывают тот срез. Текущие исправления документации указаны в отчёте D0–D3; runtime findings этим не закрыты.
> [Актуальный запуск](../../../../README.md) · [Текущий план](../../../README_work_plan.md) · [Результат D0–D3](../../../stages/stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Проект: lidar_MosMetro3D. Режим: code-only с существующими локальными тестами. Тип: code-only-project-readiness. Практическая стадия — развитый исследовательский прототип; несколько исполнимых веток ещё не сведены к единой сдаваемой версии. Документация в этом отчёте не используется как доказательство реализации.

## Карта реализации

Все пути ниже относительно корня проекта. «Реализовано» означает наличие прослеженного кода; новый ROS replay этим не заявляется.

| Возможность | Первичное evidence | Фактический статус |
|---|---|---|
| Чтение PointCloud2 | `src/cloud_input.py`, `scripts/archive_bag_frames.py`, `scripts/audit_bag.py` | Schema/offset/endian/row padding, finite/non-zero; archive reader; отдельные source frames. Python input tests прошли. |
| Python envelope baseline | `src/stage_3_baseline.py`, `config/geometry_contract.yaml`, `config/geometry_new_data_experiment.yaml` | Assumed envelope, voxel components, floor/grade/track hypotheses, nearest и JSON/diagnostics; это самостоятельная ветка. |
| C++ rail-axis | `src/cpp/auto_rails_core.*` | Два выбора пар: baseline и development_candidate; текущий default — development_candidate. Search defaults 2–80 м, station 2 м, cell 0,04 м; это не подтверждённая дальность детекции. |
| C++ envelope | `src/cpp/curve_envelope_core.*` | CORE/MARGIN/OUTSIDE/UNKNOWN, ближайшие source points, wireframe; default tangent extension, optional arc_limited и arc_clamped. |
| Отделение reportable/noise | `ApplyCoreNoiseFilter` и `ApplyFrozenNoiseTreeV1` в C++ core | Raw CORE неизменен. Legacy: min 22, r=0,25, span≤1,0, avg axis distance≤1,20. Frozen model: extent_z>0,3665030598640442 и count>104. Это два разных правила сигнала. |
| ROS2 C++ | `src/lidar_mosmetro3d_cpp/src/curve_envelope_node.cpp` | PointCloud2 subscriber, JSON String publisher, параметры/проверки, legacy reportable decision; `system_status=UNKNOWN`, safety=false. ROS node не загружает модель v1. |
| CUDA | `src/cpp/cuda_envelope.cu`, `.hpp`, `_stub.cpp`, `Dockerfile.cuda`, CMake | Опциональная разметка envelope; CPU default/fallback. AutoRails остаётся CPU. Свежий GPU runtime не проверялся. |
| CPU viewer | `scripts/serve_stage_2_cpu_catalog.py`, `scripts/cpu_catalog_runtime.py`, `web/stage_4_cpu_*` | 7 SOURCES; identity, matching JSON/raw, cache. Development default вызывает direct stream с моделью; baseline вызывает ROS node. |
| Browser research geometry | `web/stage_2_auto_rails.js`, `stage_2_review_layers.js`, `stage_3_live_envelope.js`, `stage_3_objects.js` | Auto/manual axis, membership, controls и object candidates. Эти алгоритмы не равны автоматически CPU viewer или ROS runtime. |
| Обучение модели | `scripts/train_noise_classifier.py`, `models/noise_classifier_doubleT_obstacle_v1.json` | Собственное CART-подобное дерево; training rows из 201 кадров, largest reportable component в positive interval. C++ frozen thresholds вшиты в код: переобучение JSON само по себе не обновляет C++ inference. |
| Оценка | `scripts/evaluate_noise_classifier.py`, `src/stage_3_metrics.py`, audit/summarize scripts | Есть frame-level development counts, timings, candidate windows; общего независимого object/event evaluator со split manifest в просмотренном коде не найдено. |
| Синтетические препятствия | `src/synthetic_obstacle_generator.py`, `config/synthetic_obstacles_development.yaml` | Box/cylinder ray casting, first-return occlusion, исходная schema и timestamps, ground-truth JSON, ROS wrapper. 10 имеющихся generator tests прошли в локальном suite. |
| Видео и полный offline catalog | `scripts/export_full_cpp_catalog.py`, merge/render/concat scripts | Экспорт, identity/hash, previews и главы видео. MP4 в `artefacts/stage_4/.../previews/` существуют; финальное демонстрационное видео не просмотрено. |
| Motion diagnostics | `scripts/estimate_new_data_lidar_motion.py`, `probe_new_data_sleeper_phase.py`, `analyze_new_data_motion.py` | Offline диагностика. Нет включения этой оценки в validated deskew, tracking или TTC. |
| Упаковка | `Dockerfile`, `src/lidar_mosmetro3d_cpp/CMakeLists.txt`, `scripts/validate_stage_*.ps1` | Humble/Jammy, colcon package; CMD запускает `audit_bag.py --help`. Скрипты разработки не являются готовым универсальным Linux release entrypoint. |

## Три исполнимых пути

```text
Python baseline:
  ROS2 PointCloud2 -> cloud_input -> YAML envelope/voxel components
  -> /stage_3/obstacle_candidate + /stage_3/diagnostics

C++ ROS node:
  ROS2 PointCloud2 -> AutoRails -> envelope -> legacy noise filter
  -> /stage_3/curve_envelope_candidate (JSON String)

Default CPU catalog:
  TAR/SQLite -> XYZF -> DirectDetailedCpuRuntime -> C++ stream CLI
  -> model_v1 reportable split -> HTTP -> CPU viewer
```

`ros2 run ... curve_pipeline_stream_cli` здесь только запускает executable; данные идут через stdin/stdout, а не через ROS subscriptions. CPU viewer по умолчанию использует backend model split; legacy viewer-ветка содержит собственные компоненты/temporal confirmation и может иначе рассчитывать display distance. Raw membership остаётся C++ результатом, но тезис «viewer никогда ничего не классифицирует» для всех режимов слишком широк.

## Наиболее существенные findings

| Приоритет | Finding | Evidence / сила утверждения | Действие |
|---|---|---|---|
| P1 | Timing складывает уже измеренное время повторно; lean выполняет обе фильтрации и wireframe | `curve_pipeline_stream_cli.cpp:209–260`, direct code contradiction | Разнести timers/stages; считать один активный путь; повторить одинаковый replay. |
| P1 | Viewer model и ROS legacy расходятся по signal policy | `serve_stage_2_cpu_catalog.py:77`, `cpu_catalog_runtime.py:180`, node `:247` | Зафиксировать release method/config и доказать parity конечных решений. |
| P1 | Общий test entrypoint требует внешнего HTTP server | `tests/test_dataset_catalog_http.py:9`, `scripts/validate_stage_3.ps1:15`; три ConnectionRefused в новом запуске | Разделить unit/integration lifecycle. Это дефект воспроизводимости проверки, не доказательство отказа алгоритма. |
| P1 | CLI Python принимает `--geometry-config`, но обычный запуск его не передаёт | `stage_3_baseline.py:573–593`, constructor `:538–546`, direct code contradiction | Узкая проверка CLI → node config, затем адресное исправление отдельной задачей. ROS parameter — отдельный рабочий канал настройки. |
| P2 | Direct runtime игнорирует timeout и блокируется в readline | `cpu_catalog_runtime.py:240–250`, сервер держит runtime_lock | Fault-injection с зависшим worker; deadline/restart/UNKNOWN после подтверждения. Зависание сейчас не воспроизводилось. |
| P2 | Requirements не покрывает прямые imports | `requirements.txt`: numpy/matplotlib; `yaml` в baseline/generator/archive, SciPy в части diagnostics | Явно разделить local core/research и ROS system dependencies; clean-env import-check. Наличие yaml в текущей .venv не исправляет manifest. |
| P2 | Скрытые зависимости viewer на локальные artefacts | vendor files читаются из `artefacts/stage_4/cpu_viewer/vendor`, archives заданы SOURCES | Проверить clean clone/image без рабочего каталога автора; добавить воспроизводимую подготовку. |
| P2 | Defaults не едины | Launcher/node/AutoRails: 2,0; `DirectDetailedCpuRuntime.__init__`: 3,0 | При запуске launcher передаёт 2,0 явно, поэтому default UI этим не сломан. Другие callers могут получить иную ось; централизовать конфигурацию. |

Mandatory bug discovery выполнен: прослежены input → decision → output, CLI/config, таймеры, exception/timeout и потребители JSON. Подробнее и порядок test-first — [bug audit](bug-audit-2026-09-23.md). Продуктовых исправлений и новых воспроизводящих тестов здесь нет.

## Проверки и границы готовности

Команды: `rg`, `Get-Content`, git status/diff; `.venv/Scripts/python.exe --version` и import dependencies; Python unittest discovery; Node --test всех `test_*.cjs`; чтение семи JSON summaries и saved timing. Полные команды и stdout — в [индексе](index.md) и его evidence links.

- Node: 58/58 PASS; Python: 71 OK из 75 items, 4 environment/integration errors. Старое падение JS lifecycle из отчётов 20 сентября в этом запуске не повторилось.
- Сохранённые данные семи источников: 13 759 кадров; sum legacy negative alarms=4 797, model=457, UNKNOWN=193. Наличие этих files подтверждает сохранённые counters, не валидность физической разметки и не новый runtime.
- В репозитории есть код и unit evidence, но нет доказательства независимого recall, допустимой false-alarm rate, реального предельного detection range или производительности на i7-9700E/RTX 4070 Ti SUPER.
- Deskew, background map subtraction, tracking/TTC и calibrated risk не активны в выбранном C++ пути; research motion scripts их не реализуют.

Уровень L1 для перечисленных локальных проверок; L0 для остальных findings. Отдельно не проверены свежая Docker-сборка, C++ tests после стороннего tangent patch, ROS bag delivery/queue/drops, GPU, браузерное отображение и стенд. Остаточный риск — провести демонстрацию одним вычислительным путём, а сдать другой. Следующий минимальный тест: фиксированный config и четыре контрольных случая через ROS node и default viewer с таблицей решений и raw/reportable counts.
