# lidar_MosMetro3D — код и интеграция

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Датированный аудит до редакции D0–D3; findings и рекомендации описывают тот срез. Текущие исправления документации указаны в отчёте D0–D3; runtime findings этим не закрыты.
> [Актуальный запуск](../../../../README.md) · [Текущий план](../../../README_work_plan.md) · [Результат D0–D3](../../../stages/stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Дата: 2026-09-20. Audit mode: code-only + существующие узкие тесты. Report type: code-only-project-readiness. Категория: project-readiness. Цель: установить, что делает исполняемая система, не опираясь на README или старые аудиты.

**Technical prototype / HOLD для готовности финального конвейера.** Реализован последовательный Python-путь от PointCloud2 до кандидатных кластеров, расстояния и ROS diagnostics. Также реализована отдельная JS-ветка с покадровой парой рельсов, локальным габаритом и объектными компонентами. Визуальный результат второй ветки не является автоматически результатом первой.

Validation level: L1 для перечисленных тестов; L0 для остальных code findings. Validation basis: 28 Python PASS, 15/16 JS PASS, один HTTP-тест ERROR в доступном контейнере. Исторические JSON дают доказательство прошлых выборочных запусков, а не runtime текущей версии.

## Карта и реализованные задачи

| Задача из кода | Evidence | Область результата |
|---|---|---|
| Декодирование облака с реальными offsets/stride/endian | `src/cloud_input.py:point_view, inspect_cloud`; `tests/test_cloud_input.py` | Есть обработка padding, нулей/NaN и исходных timestamps |
| Python-кандидаты, компоненты и расстояния | `src/stage_3_baseline.py:evaluate_cloud, candidate_envelope_masks` | Объединение прямого/grade/track габаритов, 26-neighbour voxels; candidate-only, без проверенного negative detector |
| ROS2-подписчик и публикация | `baseline_node_class`, `scripts/run_stage_3_baseline.py` | PointCloud2 → String JSON + DiagnosticArray; параметры топика/конфига есть у node |
| Replay-проверка | `scripts/replay_stage_3_baseline.py`, `scripts/validate_stage_3.ps1` | Подсчёт результатов, замедленный replay; helper ограничен одной db3 и не принимает отдельный geometry config |
| Интерактивный viewer и текущая геометрия | `web/stage_2_raw_player.html`, `stage_2_review_layers.js`, `stage_2_auto_rails.js`, `stage_3_live_envelope.js`, `stage_3_objects.js` | Другая вычислительная ветка по XYZ; нет установленной идентичности её решений ROS2-ветке |
| Ленивый просмотр большого архива | `scripts/serve_stage_2_catalog.py` | Ограниченный cache и проверка количества сообщений; у new_data geometry_enabled=false |
| Метрики development-окна | `src/stage_3_metrics.py` | Длительность, candidate-frame rate, processing percentiles; не event evaluator TP/FP/FN |
| Упаковка | `Dockerfile`, `.dockerignore`, `requirements.txt` | ROS Humble/Jammy; Python source/config/tests/web копируются в образ. Новая чистая сборка не проверялась |

Нет отдельного облачного backend, БД приложения или внешнего inference API в рассмотренном пути. SQLite используется как read-only источник bag. Новые сети и ML-зависимости не нужны для уже реализованного baseline.

## Основные пробелы по важности

**HIGH — разные источники решения.** Python `candidate_envelope_masks` объединяет несколько гипотез и допускает прямой fallback на большом ROI; JS `createEnvelope` ограничен текущим рельсовым сегментом. Margin/core, отбор маленьких групп и семантика статусов различаются. `stage_2_review_layers.js` одновременно умеет показывать сохранённый `frame.stage_3_baseline` и вычислять live-состояние. Это допустимо для лаборатории, но без выбора одной ветки нельзя считать демонстрацию доказательством работы сдаваемого контейнера.

**HIGH — detector product gap.** `evaluate_cloud` выдаёт кандидаты либо UNKNOWN; `contract_issues` принимает только ASSUMED_HACKATHON, а не готовый VERIFIED режим. Это сознательные ограничения, не баг, который можно исправить переименованием UNKNOWN. В `stage_3_metrics.py` нет event matching или расчёта FP/FN; качество пока нельзя установить автоматически этим evaluator.

**HIGH — ограничения пути и дальности.** `stage_2_auto_rails_config.json` ограничивает поиск forwardMax=80; фактический сегмент ещё короче. `stage_3_objects_config.json` разрешает поиск до 200 м, но прямой source-X lateral gate и пороги пола не доказывают работу на кривой или 200 м. Метрики дальности единичных возвратов, компоненты и уверенного обнаружения различаются.

**HIGH — воспроизводимость запуска.** `validate_stage_3.ps1` запускает общий unittest discovery, куда входит тест внешнего HTTP-каталога на localhost:8080, но не поднимает его. Существующий тест в контейнере ERROR/ConnectionRefused. Кроме того, `main()` baseline принимает `--geometry-config`, но для обычного запуска не передаёт его в `run_node()` / конструктор. ROS-параметр — отдельный путь настройки, его это статическое замечание не отменяет.

**MEDIUM — неподтверждённый runtime перенос.** Offline `experiment_new_data_baseline.py` вызывает evaluate_cloud напрямую. Результат на 101 кадре не доказывает QoS/очередь/потери для новой записи через ROS2. Исторический `stage_3_replay.json` содержит playback_rate=0.15, поэтому его 201/201 нельзя выдавать за темп исходного потока.

**LOW — тест/интерфейс расходятся.** `tests/test_auto_rails.cjs:75` ожидает «Автоось», а UI при найденной оси оставляет строку пустой. Тест падает; ошибка вычисления рельсов этим не доказана.

## Первичные артефакты

- `artefacts/stage_3/stage_3_replay.json`: 201/201 результатов, все candidate, rate 0.15.
- `artefacts/stage_3/new_data_transfer/baseline_1050_1150/summary.json`: 101/101 candidate, p95 248.66 мс, quality_metrics=null.
- `.../visual_replay.json`: AutoRails 100/101, system UNKNOWN, p95 59.41 мс только локального JS-расчёта.
- `artefacts/stage_3/obstacle_membership/coverage.json`: оба отмеченных объекта UNKNOWN относительно поддержанного пути; event_recall/fp_per_min=null.
- `artefacts/stage_3/object_candidates/full_replay.json`: source anchors входят в компоненты. Это полезный результат, но не полнота объекта и не event recall.

## Команды

```text
Get-Content src/stage_3_metrics.py
Get-Content scripts/validate_stage_3.ps1 -TotalCount 145
Get-Content Dockerfile
node --test tests/test_auto_rails.cjs tests/test_live_envelope.cjs tests/test_object_candidates.cjs
docker exec --env PYTHONDONTWRITEBYTECODE=1 --env PYTHONPATH=/workspace/src:/workspace/tests lidar-player-catalog-8081 python3 -m unittest discover -s /workspace/tests -p test_new_data_profile.py -v
docker exec --env PYTHONDONTWRITEBYTECODE=1 --env PYTHONPATH=/workspace/src:/workspace/tests lidar-player-catalog-8081 python3 -m unittest test_stage_3_baseline test_stage_3_metrics test_geometry_contract test_cloud_input -v
docker exec --env PYTHONDONTWRITEBYTECODE=1 --env PYTHONPATH=/workspace/src:/workspace/tests lidar-player-catalog-8081 python3 -m unittest test_dataset_catalog_http.DatasetCatalogTests.test_catalog_identity_and_geometry_isolation -v
```

Mandatory bug discovery: см. [отдельный отчёт](bug-audit-2026-09-20.md). Ближайшая техническая серия: воспроизводимый test entrypoint и профиль → один вычислительный путь → отрицательные/положительные контрольные сценарии. Backlog: косметика viewer и необязательные алгоритмы.

Не проверены чистый rebuild, полный новый ROS2 replay, независимые данные и длительная нагрузка. Исходники/тесты не менялись. Остаточный риск — подмена продукта набором несвязанных экспериментальных веток. Минимальный следующий тест: одна конфигурация и один bag должны давать идентичные сохранённые/ROS2/отображаемые результаты по frame и timestamp.
