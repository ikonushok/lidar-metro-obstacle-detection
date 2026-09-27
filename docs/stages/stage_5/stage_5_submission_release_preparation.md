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
- Validation level achieved: L1 для unit-тестов gate; L0 для полного
  соответствия ТЗ до чистого Docker/ROS2 replay.
- Что не проверено: финальный Docker build, полный ROS2 replay, p95/p99,
  drops/resources, открытие публичной ссылки из инкогнито, финальные видео и
  презентация.
- Известные FP/FN или safety-риски: качество детекции не менялось; прежние
  ограничения `UNKNOWN != CLEAR`, assumed geometry и отсутствие production
  safety сохраняются.
- Следующий минимальный тест: перенести gate в сдачную копию
  `C:\Users\Ilya\PycharmProjects\lidar-metro-obstacle-detection`, выполнить
  `python scripts/check_submission_package.py`, затем Docker build/player smoke.
- Residual risk: gate защищает состав репозитория, но не доказывает runtime
  quality, real-time или соответствие скрытой проверке жюри.
