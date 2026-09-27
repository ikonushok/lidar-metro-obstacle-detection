# Stage 5: submission release preparation

## Задача

- Goal: подготовить репозиторий и документацию к сдаче без добавления локальных
  датасетов в Git.
- Наблюдаемая проблема или исходный claim: сдачная копия должна быть
  воспроизводимой для проверяющего, но текущая готовность не должна
  преувеличиваться до full production/real-time claim.
- Non-goals: менять геометрию, модель, ROS2-схемы, QoS, thresholds,
  train/test split или добавлять новые зависимости.
- Source of truth: `docs/hackathon_documentations/instruction.md`,
  `docs/hackathon_documentations/5. ДепТранспорта.pdf`, `README.md`,
  `SOLUTION.md`, фактические команды проверки.
- Пункт/раздел ТЗ и обязательный результат: публичный Git-репозиторий,
  README с локальным запуском, документация, прототип/демонстрация, Docker /
  ROS2 Humble сценарий.
- Этап docs/README_work_plan.md: финальная упаковка / release-demo.
- Целевое окружение: Ubuntu 22.04 + ROS 2 Humble + Docker; фактическая среда
  проверки на этом шаге: Windows/PowerShell для статических repo-gates и unit
  tests.
- Входные данные и единицы: локальные `dataset/raw` и `dataset/for_hackathon`;
  сами данные не tracked.
- Конкретный bag/версия/интервал, топик и объём выборки: не применимо для
  статической repo-проверки; runtime replay проверяется отдельным шагом.
- Факты из docs/README_dataset_audit.md: датасеты велики и не входят в Git;
  проверяющий должен положить их локально.
- Рабочие frames и направление transforms: не меняются.
- Режим baseline/расширений: сдачный player/headless сценарий использует
  `development_candidate`, `tangent`, `candidate_baseline_v2`; unified offline
  candidate не объявляется runtime-контрактом до отдельной интеграции.
- Временная база событий и способ измерения вычислительной задержки: не меняется.
- Allowed files: README/solution docs, submission checklist, read-only gate,
  узкие tests.
- Files to avoid: `dataset/`, `artefacts/`, raw bag/archive/video files,
  production geometry/model contracts.
- Защищённые контракты: `UNKNOWN != CLEAR`, данные не tracked, Docker/ROS2
  commands должны оставаться воспроизводимыми, safety decision не разрешает
  движение.
- Deliverables и статус каждого:
  - reviewer quickstart: exists, updated;
  - submission checklist: added;
  - read-only package gate: added;
  - final Docker/ROS2 full replay: pending separate validation;
  - public push: blocked until explicit user command.
- Путь отчёта этапа или категории:
  `docs/stages/stage_5/stage_5_submission_release_preparation.md`.
- Основной агент: `agents/lidar_obstacle_pipeline.md`.
- Нужен ли `safety_geometry_reviewer` и почему: нет, geometry/runtime contract
  не меняется.
- Нужен ли отдельный этап `validation_reviewer`: да, после изменений проверить
  evidence и не завысить уровень готовности.
- Validation target: L1 для submission gate и docs consistency; L0 для полного
  соответствия ТЗ до Docker/ROS2 replay.
- Validation method: unit tests for package gate, direct run of
  `scripts/check_submission_package.py`, static scan of tracked files.
- Acceptance criteria: gate проходит на текущем repo, tests проходят,
  документация ссылается на gate и не заявляет неподтверждённый full-ready claim.
- Stop conditions: обнаружены tracked datasets/secrets/large binaries,
  Docker/ROS2 command docs расходятся с фактическими scripts, требуется менять
  protected runtime contract.

## Отчёт о завершении

- Что изменено: добавлены `docs/README_SUBMISSION_CHECKLIST.md`,
  `scripts/check_submission_package.py`, `tests/test_submission_package_check.py`;
  `README.md`, `SOLUTION.md`, quickstart и `.gitignore` дополнены ссылками и
  repo-gate правилами.
- Evidence inspected: `docs/hackathon_documentations/instruction.md`,
  `README.md`, `SOLUTION.md`, `docs/README_REVIEWER_PLAYER_QUICKSTART.md`,
  `.gitignore`, `.dockerignore`, `agents/task_spec_short.md`,
  `agents/lidar_obstacle_pipeline.md`, `agents/validation_reviewer.md`.
- Commands run:
  - `.venv\Scripts\python.exe ...` — FAIL, локальная `.venv` ссылается на
    недоступный `Python312`; это проблема локального venv, не Docker-сценария.
  - `C:\Users\Ilya\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest tests.test_prepare_hackathon_datasets tests.test_submission_package_check`
    — PASS, 5 tests.
  - тем же Python `scripts\check_submission_package.py` в исходном рабочем
    репозитории — FAIL: найдены tracked `artefacts/` и `dataset/.gitkeep`.
    Это ожидаемое расхождение исходного research repo и чистой сдачной копии;
    gate должен проходить в `lidar-metro-obstacle-detection`.
  - в сдачной копии `scripts\check_submission_package.py` — PASS, tracked
    files: 419 до коммита gate, 423 после добавления gate.
  - в сдачной копии
    `scripts\check_submission_package.py --require-clean` — PASS на commit
    `0fd6bed`.
  - в сдачной копии
    `docker build -t lidar-metro-obstacle-detection:submission .` — PASS;
    build context 1.39 MB; image
    `sha256:c4cf115060bd918c1ae7f6347b6afce37abfb4cb73d8cb9c408c54391f63dff1`,
    size 524563646 bytes.
  - в сдачной копии
    `scripts\prepare_hackathon_datasets.py --raw-dir ...\lidar_MosMetro3D\dataset\raw --catalog-dir ...\lidar-metro-obstacle-detection\dataset\for_hackathon`
    — PASS; три архива подготовлены hardlink-ами.
  - в сдачной копии
    `scripts\run_stage_2_cpu_player.ps1 -Port 8101 ... -Image lidar-metro-obstacle-detection:submission -NoBrowser`
    — PASS; контейнер поднял HTTP-плеер на `http://localhost:8101/`.
  - `GET /datasets.json` — PASS; доступны 8 source IDs:
    `new_data`, `roundT_doubleT`, `squareT_platform_squareT_switch`,
    `doubleT_platform`, `roundT_squareT_pressureGate_squareT`,
    `doubleT_obstacle`, `roundT_pressureGate_roundT`, `cloud_with_fake_obj`.
  - `GET /api/cpu_sources/cloud_with_fake_obj/manifest.json` — PASS:
    `frame_count=1510`, `runtime_transport=direct_cpp`,
    `noise_filter_mode=candidate_baseline_v2`,
    `rail_selection_method=development_candidate`.
  - `GET /api/cpu_sources/doubleT_obstacle/13.json` — PASS:
    `intrusion_candidate_present=true`,
    `nearest_reportable_intrusion_distance_from_source_origin_m=55.568001`,
    `runtime_transport=direct_cpp`,
    `noise_filter_mode=candidate_baseline_v2`,
    `system_status=UNKNOWN`,
    `safety_decision_permitted=false`.
  - `scripts\prepare_hackathon_datasets.py --extract doubleT_obstacle` —
    PASS; в сдачной копии создан ignored
    `dataset/extracted/doubleT_obstacle` с `metadata.yaml` и
    `doubleT_obstacle_0.db3`.
  - Headless ROS2 smoke:
    `docker run ... ros2 run lidar_mosmetro3d_cpp curve_envelope_node ...`,
    затем `ros2 topic echo` и `ros2 bag play /data --rate 1.0 --read-ahead-queue-size 2`
    — PASS_WITH_RISKS. Bag info: 4.5 GiB, 20.392030296 s, 201
    `sensor_msgs/msg/PointCloud2` messages on
    `/sensing/lidar/hesai128/pointcloud`. `ros2 bag play` выдавал
    `Message queue starved` warnings на Windows/Docker bind mount и был
    остановлен вручную после smoke-части, поэтому throughput/full replay не
    заявляется.
  - ROS2 echo summary from `/tmp/candidate_echo.txt`: 45 JSON records parsed;
    `runtime_transport=ros2`,
    `noise_filter_mode=candidate_baseline_v2`,
    `system_status=UNKNOWN`,
    `safety_decision_permitted=false`,
    `alarm_seen=true`,
    `alarm_distance_m=55.580002`.
  - Full slowed ROS2 replay:
    `ros2 bag play /data --rate 0.2 --read-ahead-queue-size 2` — PASS_WITH_RISKS.
    Command completed with exit code 0. Echo summary from
    `/tmp/candidate_echo_full.txt`: 201 JSON records for 201 input
    `PointCloud2` messages, `alarms=51`, first output
    `runtime_transport=ros2`,
    `noise_filter_mode=candidate_baseline_v2`,
    `system_status=UNKNOWN`,
    `safety_decision_permitted=false`,
    first alarm distance `55.580002` m, last status
    `NO_REPORTABLE_INTRUSION_NOISE_IGNORED`. The replay still emitted repeated
    `Message queue starved` warnings on Windows/Docker bind mount, so this is
    completion/interface evidence, not real-time throughput evidence.
- Validation level achieved: L1 для unit-тестов gate, чистого repo-gate и
  Docker build; L3 для direct-player smoke на локальных hardlink-датасетах;
  L3/PASS_WITH_RISKS для headless ROS2 full slowed replay на
  `doubleT_obstacle`;
  L0/L1 для full real-time/throughput claims.
- Что не проверено: ROS2 replay без `Message queue starved`, p95/p99,
  drops/resources, открытие публичной ссылки из инкогнито, финальные видео и
  презентация.
- Известные FP/FN или safety-риски: качество детекции не менялось; прежние
  ограничения `UNKNOWN != CLEAR`, assumed geometry и отсутствие production
  safety сохраняются.
- Следующий минимальный тест: прогнать ROS2 replay на более подходящем
  диске/стенде или с подобранной очередью без `Message queue starved`, затем
  записать короткое demo video / screenshots.
- Residual risk: gate защищает состав репозитория, но не доказывает runtime
  quality, real-time или соответствие скрытой проверке жюри.
