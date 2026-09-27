# Прямой C++-плеер и отдельный ROS2-вход

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Актуальный контракт двух входов / датированный интеграционный результат. Scope проверки указан ниже; это не гарантия полного качества или скорости.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Дата: 2026-09-23. Этапы 5–6, patch → validation. Пользователь явно согласовал возврат прямого C++-пути плееру и описание в корневом README.

- Цель: development_candidate/tangent/fmin=2/model_v1 в плеере через один постоянный C++ stream-процесс, без ROS2 pub/sub; ROS2-узел с той же моделью сохраняется для §3.3/4/8.6 ТЗ.
- Источники: HEAD af9151c, текущие runtime/server/launcher, C++ stream/core/node, корневой README, ТЗ организатора.
- Non-goals: изменение модели, геометрии, порогов, QoS, labels, исправление ROS2 retry-loop или timing direct CLI, общий редизайн README.
- Allowed files: scripts/cpu_catalog_runtime.py, serve_stage_2_cpu_catalog.py, run_stage_2_cpu_player.ps1, measure_cpu_catalog_window.py, validate_ros_model_pipeline.ps1, README.md, task spec/run report.
- Защищённые контракты: исходные XYZ/frame/header, candidate-only, UNKNOWN не CLEAR, model_v1 без переобучения; working frame source <- source, преобразований нет. Wall-time измеряется monotonic.
- Совместимость: прежний явный baseline остаётся ROS2; основной development_candidate возвращается на direct. Чтение bag использует ROS-библиотеки десериализации, но direct-режим не создаёт ROS2 nodes/DDS.
- Проверки: сборка Docker, существующие CPU/catalog/JS contracts, parity direct ↔ ROS2 на контрольных кадрах; HTTP manifest/result transport=direct_cpp, препятствие 13 и шум 145; процесс stream запущен напрямую, ROS2 node отсутствует в контейнере плеера.
- Роли: текущий агент по lidar_obstacle_pipeline; отдельный validation-проход по validation_reviewer. Геометрия и правила фильтрации не меняются, новый safety-review не требуется.
- Acceptance/L3: реальные ответы HTTP подтверждают direct_cpp/model_v1/tangent, ROS2 parity сохраняется; корневой README объясняет два входа и команды.
- Артефакты: artefacts/stage_5/direct_player/. Отчёт: stage_5_direct_player_run.md.
- Stop: несовпадение решений или необходимость изменения алгоритма. Остаточный риск: прямой путь не гарантирует отсутствие задержек чтения архива; пропускная способность требует отдельного непрерывного замера.
