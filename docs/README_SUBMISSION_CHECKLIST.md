# Чеклист сдачи решения

Этот документ фиксирует порядок подготовки публичного репозитория и материалов
перед отправкой ссылки в личный кабинет. Данные `dataset/` в Git не добавляются.

Перед финальной сдачей явно фиксируется, что сдаётся `baseline_v3 runtime
pipeline`: geometry-first gate, boundary warning и temporal model-assist только
для слабых/неочевидных случаев. `candidate_baseline_v2` не называть финальной
моделью; он остаётся встроенным score assist-ветки и сравнительным фильтром.

## 1. Репозиторий

- Репозиторий содержит исходники, Dockerfile, конфиги, тесты и документацию.
- `dataset/`, `artefacts/`, `log/`, `.venv/`, `.idea/` и большие бинарные
  артефакты не tracked.
- В корне есть `README.md` с локальным запуском и `SOLUTION.md` с архитектурой,
  алгоритмом, ограничениями и результатами.
- Перед публичным push выполнен read-only gate:

```powershell
python .\scripts\check_submission_package.py
```

Для финального release-коммита дополнительно:

```powershell
python .\scripts\check_submission_package.py --require-clean
```

## 2. Данные

Проверяющий кладёт архивы в `dataset/raw/`; допустимые имена описаны в
[README_REVIEWER_PLAYER_QUICKSTART.md](README_REVIEWER_PLAYER_QUICKSTART.md).

Подготовка:

```powershell
python .\scripts\prepare_hackathon_datasets.py
```

Для ROS2/headless-сценария распаковывается только нужный bag:

```powershell
python .\scripts\prepare_hackathon_datasets.py --extract doubleT_obstacle
```

## 3. Прототип / плеер

Минимальная демонстрация текущего исполняемого `baseline_v3` runtime:

```powershell
.\scripts\run_stage_2_cpu_player.ps1 `
  -Port 8100 `
  -RailSelectionMethod development_candidate `
  -RailForwardMinM 2 `
  -ForwardExtensionMethod tangent `
  -NoiseFilterMode baseline_v3 `
  -RebuildImage
```

Открыть `http://localhost:8100/`. В плеере должны быть доступны известные
source IDs, включая `new_data`, `doubleT_obstacle` и `cloud_with_fake_obj`.

## 4. ROS2/headless-проверка

Контейнер должен собираться из чистого клона:

```powershell
docker build -t lidar-metro-obstacle-detection:submission .
```

Далее по `README.md` запускается:

```text
ros2 bag play -> curve_envelope_node -> /stage_3/curve_envelope_candidate
```

Быстрый wrapper:

```powershell
.\scripts\run_submission_ros2_demo.ps1 -BuildImage -StopExisting
```

Проверяемые признаки результата:

- публикуется JSON в `std_msgs/String`;
- есть `intrusion_candidate_present`;
- есть ближайшее расстояние или `null`;
- есть `status` / diagnostics;
- `UNKNOWN` и отсутствие кандидата не описываются как `CLEAR`;
- `safety_decision_permitted=false`.

## 5. Документация и презентация

Перед сдачей должны быть готовы ссылки или файлы:

- GitHub repository;
- документация: `SOLUTION.md` или PDF/облачный документ на его основе;
- презентация;
- прототип: ссылка на репозиторий/инструкцию или скринкаст;
- дополнительные материалы: демонстрационное видео, схемы, список ограничений.
- внутренний evidence/gap report:
  `docs/reports/submission/submission_gap_closure_20260927.md`.
- smoke report headless ROS2:
  `docs/reports/submission/headless_ros2_smoke_20260927.md`.

## 6. Stop-code

До дедлайна 29 сентября 23:59 МСК:

- открыть репозиторий или выдать гостевой доступ;
- проверить ссылку из приватного окна браузера;
- загрузить ссылки в личный кабинет;
- зафиксировать commit hash и, при необходимости, tag.

После дедлайна нельзя менять сданную ветку, презентацию, документы и прототип
по отправленным ссылкам.
