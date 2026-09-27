# Stage 5 submission player quickstart

## Задача

- Goal: подготовить короткий воспроизводимый путь для проверяющих: `dataset/raw` -> `dataset/for_hackathon` / optional `dataset/extracted` -> Docker CPU player.
- Наблюдаемая проблема или исходный claim: перед сдачей нужно прекратить улучшение пайплайна и дать простую инструкцию запуска плеера по всем текущим датасетам.
- Non-goals: не менять алгоритм, ROS2-схемы, пороги, модель, геометрию, synthetic generator или правила оценки.
- Source of truth: текущий `README.md`, `docs/README_player_setup.md`, `docs/README_dataset_describtion.md`, `scripts/serve_stage_2_cpu_catalog.py`, `scripts/run_stage_2_cpu_player.ps1`.
- Пункт/раздел ТЗ и обязательный результат: сдачная демонстрация через Docker/визуализацию; точные пункты ТЗ здесь не перечитывались.
- Этап docs/README_work_plan.md: stage 5 / demo-submission documentation.
- Целевое окружение: Ubuntu 22.04 + ROS 2 Humble + Docker; фактическая среда проверки: Windows PowerShell workspace, без runtime Docker-прогона.
- Входные данные и единицы: три локальных TAR-архива `for_hackathon`, `new_data`, `cloud_with_fake_obj`; единицы PointCloud2 не менялись.
- Конкретный bag/версия/интервал, топик и объём выборки: не применимо для изменения документации; inventory источников взят из server catalog.
- Факты из docs/README_dataset_audit.md, подтверждения на текущем входе и непроверенные предположения: `new_data` около 20 минут; `cloud_with_fake_obj` synthetic/fake obstacle source; полный runtime на текущем вводе не выполнялся.
- Рабочие frames и направление transforms: не изменялись.
- Режим baseline/расширений; необходимые TF/движение/карта/габарит и поведение при их отсутствии: не изменялись; direct player остаётся `development_candidate/tangent/candidate_baseline_v2`.
- Временная база событий и способ измерения вычислительной задержки: не изменялись.
- Allowed files: docs quickstart, preparation script, narrow static tests, this task report.
- Files to avoid: C++ core, web UI behaviour, model exports, dataset contents, artefacts.
- Защищённые контракты: `UNKNOWN` не CLEAR; source inventory не должен обещать несуществующий dataset; full extraction of `new_data` is optional and not required by direct player.
- Deliverables и статус каждого: quickstart doc implemented; dataset preparation script implemented; test alignment for eight-source catalog implemented; runtime Docker check not run.
- Путь отчёта этапа или категории: `docs/stages/stage_5/stage_5_submission_player_quickstart.md`.
- Основной агент: `agents/lidar_obstacle_pipeline.md`.
- Нужен ли `safety_geometry_reviewer` и почему: нет, safety/geometry contracts не менялись.
- Нужен ли отдельный этап `validation_reviewer`: да, текущий проход проверяет только claims и команды документации, без независимого review.
- Validation target: L1 для script/static/docs, L0 runtime.
- Validation method: unit/static tests; опционально позже Docker player smoke на машине с данными.
- Acceptance criteria: проверяющий видит куда положить raw archives, какой скрипт запустить, как стартовать Docker player, и какие sources ожидать.
- Stop conditions: не добавлять новый synthetic browser source без отдельной реализации/проверки.

## Отчёт о завершении

- Что изменено:
  - Добавлен `scripts/prepare_hackathon_datasets.py`: готовит три archive-файла для direct player и опционально распаковывает выбранные bags.
  - Добавлен `docs/README_REVIEWER_PLAYER_QUICKSTART.md`: короткая инструкция для проверяющих.
  - Обновлён статический contract test catalog на 8 источников, включая `cloud_with_fake_obj`.
- Evidence inspected:
  - `agents/context_router.md`, `agents/task_spec_short.md`, `agents/lidar_obstacle_pipeline.md`.
  - `README.md`, `docs/README_player_setup.md`, `docs/README_dataset_describtion.md`, `docs/README_synthetic_obstacles.md`.
  - `scripts/serve_stage_2_cpu_catalog.py`, `scripts/run_stage_2_cpu_player.ps1`, `scripts/extract_stage_1.py`, `scripts/extract_bag_from_tar.py`.
- Commands run:
  - `python` / `py` / `.venv\Scripts\python.exe` attempts failed in this Windows shell: no PATH Python, no installed py launcher target, broken venv launcher.
  - Bundled Python: `python -m unittest tests.test_prepare_hackathon_datasets tests.test_stage_4_all_sources_contract` — PASS, 9 tests.
  - Bundled Python: `scripts/prepare_hackathon_datasets.py` — PASS on current local dataset, all three catalog archives present.
  - Bundled Python: `scripts/prepare_hackathon_datasets.py --extract doubleT_obstacle --extract cloud_with_fake_obj` — PASS, existing extracted files skipped.
- Validation level achieved: L1 for script/static/docs; L0 for Docker/browser runtime.
- Что не проверено: Docker build/run, browser visual smoke, real archive preparation on a clean checkout.
- Известные FP/FN или safety-риски: не применимо к изменению; documentation repeats that `UNKNOWN` / no reportable candidate is not CLEAR.
- Следующий минимальный тест: запустить prepare script on current local dataset and static unit tests; затем player smoke on port 8100.
- Residual risk: собственные synthetic artifacts are documented as not yet exposed as a browser source.
