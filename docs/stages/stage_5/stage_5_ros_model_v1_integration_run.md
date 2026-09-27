# ROS2 + model_v1: результат интеграции

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Частично замещённая интеграция: ROS2 node с model_v1 сохранён; DDS-транспорт плеера заменён direct_cpp. Старые ROS HTTP-измерения относятся к прежнему плееру.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Дата: 2026-09-23. Этапы 5–6. Цель: PointCloud2 → AutoRails → tangent envelope → CORE components → frozen model_v1 → ROS2 JSON → CPU player.

## Что изменено

- `src/lidar_mosmetro3d_cpp/src/curve_envelope_node.cpp`: параметр `noise_filter_mode=model_v1` по умолчанию; вызов существующего `ApplyFrozenNoiseTreeV1` после расчёта CORE без предварительного legacy-подавления. `legacy` доступен явно. Добавлены поля `runtime_transport`, `noise_filter_mode`, `noise_filter_name`; UNKNOWN также сохраняет transport/mode.
- `scripts/cpu_catalog_runtime.py`, `serve_stage_2_cpu_catalog.py`: плеер публикует PointCloud2 и получает результат ROS2-узла; проверяет timestamp/frame/config/mode. DirectDetailedCpuRuntime сохранён для сравнения.
- `scripts/run_stage_2_cpu_player.ps1`, `measure_cpu_catalog_window.py`: mode передаётся в ROS2 и измерение; имя контейнера содержит `ros2`, поэтому старый direct-контейнер не принимается за новую версию.
- `scripts/check_ros_model_pipeline.py`, `validate_ros_model_pipeline.ps1`: воспроизводимая проверка реального ROS2 и HTTP-плеера. Исторический smoke явно запускает legacy.

Изучены перечисленные файлы, `src/cpp/curve_envelope_core.*`, stream CLI, `web/stage_4_cpu_player.js`, контракты каталога/плеера, DDS-профили, сохранённые XYZF doubleT_obstacle и исходный PointCloud2 из extracted bag. Дерево модели, его признаки и пороги здесь не менялись. Соседние изменения arc_clamped выполнялись отдельно; в этой задаче проверен tangent. Общие README/план не финализировались.

Плеер использует индексы obstacle/noise из ROS2 model_v1; существующий JS `backendModelSplit` не применяет к ним legacy-пороги/temporal controls. Результат — кандидат препятствия, `system_status=UNKNOWN`, `safety_decision_permitted=false`; отрицательная классификация не является CLEAR.

## Выполненные проверки

Артефакты: `artefacts/stage_5/ros_model_v1_integration/`.

| Проверка | Результат |
|---|---|
| Docker build + colcon, итоговый launcher на 8110 | PASS, 1 пакет; `launcher.log` |
| ROS2 ↔ direct model_v1, 33 поля на кадрах 0/13/64/145/185 | PASS; `parity.json`, `validation.log` |
| Отсутствует ось / поле y / неверный frame | UNKNOWN, candidate=null, safety=false |
| Смена lidar_livox ↔ hesai_lidar на синтетическом неподдержанном входе | PASS; проверен lifecycle, не качество Hesai |
| Исходный PointCloud2, 26 байт/точку, 921600 точек, кадр 13 | PASS с SHM; индексы obstacle/noise и ближайшая точка совпали с compact-reference |
| HTTP doubleT_obstacle: кадр 13 / 145 | 121 / 0 reportable CORE points, true / false; transport=ros2, mode=model_v1 |
| CPU runtime/launcher unittest | 11 PASS, `python_tests.log` |
| Каталог всех источников unittest | 7 PASS, `catalog_tests.log` |
| JS distance/noise/envelope tests | 14 PASS, `viewer_tests.log` |
| ROS2 smoke с явным legacy, saved frame 13 | PASS, `legacy_smoke.log` |
| git diff --check | PASS |

Итоговый образ `lidar-mosmetro3d:stage-4-cpu-viewer`: manifest list `sha256:10ae49012d6517c129442ca4f3a7cbe65f32860780716027c0e0d73c2e53b83d`. Окружение Docker Ubuntu 22.04 / ROS 2 Humble. Windows .venv не используется для запуска этих проверок.

В первом прогоне UDP-профиль `fastdds_udp_smoke.xml` успешно передал compact XYZ, но полный PointCloud2 не дал ответа за 30 секунд (`parity.log`). Повтор с существующим профилем `/app/config/fastdds.xml` (SHM + UDP) и `--shm-size=512m` прошёл (`parity_shm.log`). Валидатор использует этот профиль образа. Плеер передаёт compact XYZ и прошёл HTTP-проверку с его прежним UDP-профилем. Доставку полных облаков через UDP/между машинами этот результат не подтверждает.

Фактически выполненные основные команды из корня проекта:

```powershell
.\scripts\run_stage_2_cpu_player.ps1 -Port 8110 -RailForwardMinM 2 -ForwardExtensionMethod tangent -NoiseFilterMode model_v1 -NoBrowser -RebuildImage
.\scripts\validate_ros_model_pipeline.ps1 -Port 8110
node --test tests/test_cpu_viewer_distance_and_noise.cjs tests/test_cpu_viewer_envelope_geometry.cjs
git -c safe.directory=C:/Users/Ilya/PycharmProjects/lidar_MosMetro3D diff --check
```

Python unittest выполнялись в Docker, с readonly mount проекта в `/workspace`, cwd `/workspace`: `python3 -m unittest discover -s tests -p "test_*cpu*py" -v`; отдельно `-p test_stage_4_all_sources_contract.py` с `PYTHONPATH=/workspace/scripts:/workspace/src`. Smoke: `python3 /app/tests/smoke_curve_envelope_node.py --xyzf /workspace/artefacts/stage_2/player_doubleT_obstacle/frames/frame_0013.xyzf --noise-filter-mode legacy`, domain 173, SHM 512m.

## Запуск пользователем

Из корня проекта, Docker Desktop должен работать:

```powershell
docker ps -q --filter "publish=8100" | ForEach-Object { docker stop $_ }
.\scripts\run_stage_2_cpu_player.ps1 `
  -Port 8100 `
  -RailForwardMinM 2 `
  -ForwardExtensionMethod tangent `
  -NoiseFilterMode model_v1 `
  -RebuildImage

.\scripts\validate_ros_model_pipeline.ps1 -Port 8100
```

Открыть http://localhost:8100/, выбрать doubleT_obstacle. Контроль: кадр 13 — obstacle, кадр 145 — noise; слой шума включается существующим переключателем. Первое чтение архива включает извлечение SQLite и может быть заметно дольше обработки кадра.

Валидатор требует имеющиеся `artefacts/stage_2/player_doubleT_obstacle`, `dataset/extracted/doubleT_obstacle` и архивы каталога. Проверка ROS2 без работающего HTTP-плеера: `./scripts/validate_ros_model_pipeline.ps1 -SkipViewerCheck`.

В плеере топики: `/cpu_catalog/development_candidate/cloud` (PointCloud2) и `/cpu_catalog/development_candidate/candidate` (std_msgs/String с JSON). Сам узел принимает `input_topic`, `output_topic`, `source_frame`; его самостоятельные defaults — Hesai input и `/stage_3/curve_envelope_candidate`. Плеер задаёт собственные топики и frame выбранного источника автоматически.

## Review и границы доказательств

Safety-review отдельным проходом текущего агента: PASS_WITH_RISKS. Сохранены raw CORE, единицы/frames/header, модель применяется единожды; неизвестный вход не превращается в отрицательное решение. Геометрия assumed и фильтр обучен на development-сценарии; физическая безопасность не подтверждена.

Validation отдельным последующим проходом: L1 для узких тестов, L3 для проверенной цепочки Docker → ROS2 → HTTP и контракта отображения. Ручная WebGL-проверка в браузере, полный replay семи источников, CUDA, sustained rate/latency, live sensor и независимое качество модели не проверялись. Положительный интервал 13–64 принят как development-разметка, весь интервал в этой интеграционной проверке не пересчитывался.

Остаточный риск: совпадение двух entrypoints общей модели не доказывает её обобщение; транспорт больших облаков зависит от DDS-профиля. Следующий минимальный шаг: открыть контрольные кадры в плеере; после завершения алгоритма — непрерывный ROS2 replay и независимые сценарии с разметкой, без изменения порогов по тестовым данным.
