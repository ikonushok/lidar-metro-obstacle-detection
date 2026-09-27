# Черновик SOLUTION.md

Дата: 2026-09-24. Этап 5, режим `documentation`.

## Задача

- Goal: подготовить корневой `SOLUTION.md` в стиле указанных write-up: постановка задачи, данные, архитектура, ключевые решения, текущие результаты, ограничения, воспроизводимость и места для финальных графиков/таблиц.
- Наблюдаемая проблема или исходный claim: в проекте уже есть реализованный MVP-путь `development_candidate -> tangent -> raw CORE -> components -> model_v1`, но нет единого solution-документа для хакатона.
- Non-goals: не запускать новые replay/training, не менять runtime, модель, геометрию, thresholds, ROS2-интерфейсы, README или артефакты; не заявлять финальную готовность, independent recall, production safety или real-time полного пути без новых проверок.
- Source of truth: `README.md`, `docs/README_work_plan.md`, `docs/README_methodology.md`, `docs/README_dataset_audit.md`, `docs/README_dataset_describtion.md`, `docs/README_noise_classifier.md`, `docs/README_train_clearance.md`, отчёты `stage_5_direct_player_run.md` и `stage_5_ros_model_v1_integration_run.md`.
- Пункт/раздел ТЗ и обязательный результат: Ubuntu 22.04 + ROS 2 Humble + Docker; демонстрация через `ros2 bag play`; исходники/контейнер, описание метода, результаты экспериментов, видео и демонстрация. В текущей задаче описывается только подтверждённая часть решения.
- Этап `docs/README_work_plan.md`: stage 5, подготовка материалов описания решения до финальных проверок stage 6-8.
- Целевое окружение: Ubuntu 22.04 + ROS 2 Humble + Docker; фактическая среда проверки этой задачи: документационная правка без runtime-запуска.
- Входные данные и единицы: ROS2 `PointCloud2`, source XYZ в `m_ASSUMED`; физическая калибровка, extrinsics и путь поезда остаются неподтверждёнными.
- Конкретный bag/версия/интервал, топик и объём выборки: используются только ранее задокументированные числа; новые bag не читаются.
- Факты из `docs/README_dataset_audit.md`: семь source ID из двух архивов; `doubleT_obstacle` 13-64 включительно — development positive interval; независимый positive test отсутствует.
- Рабочие frames и направление transforms: текущий запуск работает в source frame; физический `target <- lidar` не калиброван; отсутствие CLEAR сохраняется.
- Режим baseline/расширений: действующий `development_candidate / tangent / model_v1`; deskew, карта, tracking, TTC, CUDA и arc-режимы не являются default.
- Временная база событий и способ измерения вычислительной задержки: в документе указываются только уже измеренные offline/lean timing; bag/header/per-point clocks не смешиваются.
- Allowed files: `SOLUTION.md`, этот stage-документ.
- Files to avoid: runtime source, configs, модель, README, артефакты, исходные bag.
- Защищённые контракты: `UNKNOWN` не `CLEAR`; отрицательный `model_v1` не свободный путь; 80 м - параметр габарита, не detection range; расстояние от source origin не расстояние от носа поезда.
- Deliverables и статус каждого: `SOLUTION.md` создан как черновик с заполненными доказанными разделами и TODO-плейсхолдерами.
- Путь отчёта: `docs/stages/stage_5/stage_5_solution_draft.md`.
- Основной агент: `agents/lidar_obstacle_pipeline.md`.
- Нужен ли `safety_geometry_reviewer`: нет, геометрия и runtime не меняются.
- Нужен ли отдельный этап `validation_reviewer`: да, как проверка корректности claims по документам; без новых runtime claims выше L0/L1.
- Validation target: L0 для структуры и ссылочной согласованности; L1 только для уже существующих проверок, явно ограниченных их отчётами.
- Validation method: статическое чтение документов и проверка Markdown-файла; новые тесты не запускать.
- Acceptance criteria: `SOLUTION.md` не противоречит текущим ограничениям и оставляет явные места для недостающих графиков, финальных метрик и схем.
- Stop conditions: остановиться перед изменением алгоритма, модели, геометрии, конфигов или утверждением финального качества без новых проверок.

## Отчёт о завершении

- Что изменено: создан корневой `SOLUTION.md` с описанием текущего решения и TODO-плейсхолдерами; добавлены две Archify-схемы в `assets/solution/` и ссылки на SVG/HTML в `SOLUTION.md`; создан этот отчёт.
- Evidence inspected: перечисленные source-of-truth документы, референс-статья Andrey Lukyanenko и два примера `SOLUTION.md` из GitHub; локальные `archify` schema/example files.
- Commands run: чтение документов, `git status`, сетевое чтение двух GitHub raw-файлов, статическая проверка Markdown; `archify validate` и `archify deliver` для workflow/architecture; `archify visual-check` для обоих HTML.
- Validation level achieved: L0 для нового документа; Archify delivery: showcase 9/9 checks для обеих схем; visual-check pass для 1440×900, 1600×1000, 1920×1080, 2048×1320. Существующие L1/L3 runtime claims перенесены только с явными границами из исходных отчётов.
- Что не проверено: новый runtime, финальная сборка, long ROS2 replay, независимые positive сценарии, видео, финальные графики.
- Известные FP/FN или safety-риски: `model_v1` может подавить низкие/малые препятствия; один real positive event использован в development; `UNKNOWN` сохраняется.
- Следующий минимальный тест: после завершения алгоритма выполнить чистую сборку/headless ROS2 replay и обновить разделы результатов.
- Residual risk: параллельные изменения в рабочем дереве могут изменить runtime/метрики; перед финальной сдачей документ нужно синхронизировать с зафиксированной версией.

## Дополнение 2026-09-25: синхронизация с текущим baseline

- Goal: обновить `SOLUTION.md` после проектных изменений вокруг `candidate_baseline_v2` и temporal evaluator, не меняя runtime-алгоритм.
- Наблюдаемая проблема: корневой `SOLUTION.md` и две схемы всё ещё описывали `model_v1` как актуальный runtime baseline, тогда как текущая документация и код используют `candidate_baseline_v2 / random_forest_lite`; evaluator теперь явно различает `causal_runtime` и диагностический `legacy_adjacent`.
- Non-goals: не переобучать модель, не менять геометрию, thresholds, ROS2 temporal policy, датасет или runtime source; не заявлять independent recall/full real-time.
- Source of truth: `docs/README_noise_classifier.md`, `scripts/evaluate_noise_model_candidates.py`, `scripts/evaluate_synthetic_noise_model_candidates.py`, `tests/test_evaluate_noise_classifier.py`, `src/cpp/candidate_baseline_v2_model.inc`, `src/lidar_mosmetro3d_cpp/src/curve_envelope_node.cpp`, существующие `assets/solution/*.json`.
- Allowed files: `SOLUTION.md`, `assets/solution/*`, этот stage-документ.
- Защищённые контракты: `UNKNOWN != CLEAR`; текущие `193` FP в seven-source candidate table включают `UNKNOWN`; `52/52` остаётся development evidence, не independent recall; lean p95 не доказывает full-path real-time.
- Что изменено: `SOLUTION.md` переписан с актуальным baseline `candidate_baseline_v2`, обновлены таблицы development-сравнения и lean timing, команды запуска переведены на `candidate_baseline_v2`, добавлен статус offline temporal modes; Archify JSON/HTML/SVG схемы пересобраны с `candidate_baseline_v2` и `ApplyCandidateBaselineV2`.
- Evidence inspected: `agents/context_router.md`, `agents/lidar_obstacle_pipeline.md`, `agents/validation_reviewer.md`, `docs/README_noise_classifier.md`, текущие diff-изменения evaluator/tests, runtime grep по `candidate_baseline_v2`, Archify `SKILL.md`, схемы/examples/schema.
- Commands run:
  - `node ... archify.mjs validate workflow assets/solution/obstacle_pipeline.workflow.json --quality showcase --json` — PASS, 9/9 checks, 0 errors, 0 warnings.
  - `node ... archify.mjs deliver workflow ... obstacle_pipeline.html --quality showcase --json` — PASS, 9/9 checks.
  - `node ... archify.mjs visual-check assets/solution/obstacle_pipeline.html --json` — PASS для 1440x900, 1600x1000, 1920x1080, 2048x1320; visualReview остаётся `pending`.
  - `node ... archify.mjs validate architecture assets/solution/runtime_architecture.architecture.json --quality showcase --json` — PASS, 9/9 checks, 0 errors, 0 warnings.
  - `node ... archify.mjs deliver architecture ... runtime_architecture.html --quality showcase --json` — PASS, 9/9 checks.
  - `node ... archify.mjs visual-check assets/solution/runtime_architecture.html --json` — PASS для 1440x900, 1600x1000, 1920x1080, 2048x1320; visualReview остаётся `pending`.
  - Chrome headless screenshots of standalone `obstacle_pipeline.svg` and `runtime_architecture.svg` — PASS by visual inspection: обе SVG рендерятся как схемы, не как чёрные/пустые блоки.
  - `.\.venv\Scripts\python.exe -m unittest tests.test_evaluate_noise_classifier` — PASS, 6 tests.
- Validation level achieved: L0 для `SOLUTION.md` и схемной согласованности; L1 для узкой проверки evaluator temporal tests. Старые runtime/evaluation claims не повышались.
- Что не проверено: новый full seven-source runtime replay после правки evaluator, full ROS2 replay, clean Docker build, independent positive scenario, финальные графики и видео.
- Известные FP/FN или safety-риски: positive interval остаётся development-only; `candidate_baseline_v2` может не обобщиться на low/thin/новые объекты; `UNKNOWN` сохраняется как не-CLEAR.
- Следующий минимальный тест: после фиксации финальной версии выполнить clean Docker/Humble run и full-path ROS2 replay с queue/drops/p95, затем добавить финальные графики.
- Residual risk: в рабочем дереве отдельно присутствуют незакоммиченные изменения evaluator/tests; этот отчёт описывает их как inspected evidence, но не подменяет финальный сохранённый прогон.

## Дополнение 2026-09-25: хронология доработок

- Goal: добавить в `SOLUTION.md` отдельный раздел с историей основных инженерных шагов решения.
- Что изменено: после архитектуры добавлен раздел `Хронология основных доработок`: geometry baseline, development event, Raw CORE/reportable split, первое дерево `model_v1`, runtime optimization, сравнение ML-кандидатов, temporal anti-flicker, synthetic path.
- Evidence inspected: текущий `SOLUTION.md`, `docs/README_noise_classifier.md`, ранее сохранённые timing/evaluation claims из stage-документа.
- Commands run: документационная правка; runtime-команды не запускались.
- Validation level achieved: L0 для структуры и согласованности формулировок.
- Что не проверено: новые замеры ускорения, full replay, independent recall.
- Residual risk: формулировка про ускорение ограничена подтверждёнными числами `73,8 -> 3,8 ms` для активного старого фильтра и `118,5 -> 49,8 ms` для lean compute path; claim `100x` не добавлен без отдельного evidence.

## Дополнение 2026-09-25: статусы split/model comparison

- Goal: уточнить в `SOLUTION.md`, что synthetic split/evaluator и model comparison уже реализованы, а не только запланированы.
- Что изменено: строки `Frozen split`, `Synthetic dataset v1`, `Сравнение моделей`, `Temporal parity` переведены в более точные статусы: реализовано для synthetic/development/fresh seven-source screening; independent real positive held-out и full real recall по-прежнему не заявляются.
- Evidence inspected: `docs/stages/stage_5/stage_5_real_fp_synthetic_model_v3.md`, `artefacts/stage_5/noise_model_candidate_current_2332b7a_legacy_adjacent_all_sources/compact_summary.json`, `artefacts/stage_5/noise_model_candidate_current_2332b7a_all_sources/compact_summary.json`.
- Commands run: чтение Markdown/JSON evidence; runtime-команды не запускались.
- Validation level achieved: L0 для корректировки статусов документа.
- Что не проверено: новый full ROS2 replay, clean Docker build, независимый real positive held-out.
- Residual risk: `legacy_adjacent` остаётся diagnostic/offline screening protocol; `causal_runtime` реализован и зафиксирован отдельно, но требует отдельной calibration/acceptance для model replacement.
