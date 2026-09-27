# ROS2 → tangent → model_v1 → CPU viewer

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Частично замещённая интеграция: ROS2 node с model_v1 сохранён; DDS-транспорт плеера заменён direct_cpp. Старые ROS HTTP-измерения относятся к прежнему плееру.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Дата: 2026-09-23. Режим patch → safety-review → validation; этапы 5–6. Пользователь явно запросил эту цепочку и команды запуска/проверки.

- Цель: C++ ROS2 node применяет существующее frozen tree v1 к CORE-компонентам; CPU player получает именно ROS2 JSON.
- Source of truth: src/cpp/curve_envelope_core.*, существующий stream model_v1, ROS2 node, CPU runtime/server/launcher; ТЗ §3–5; актуальные docs/README_work_plan.md и README_methodology.md.
- Non-goals: переобучение, изменение дерева/labels/порогов, tangent/arc геометрии, clocks/frames/QoS, исправление timing отдельного direct benchmark, финализация общей документации.
- Режим: rail_selection_method=development_candidate, rail_forward_min_m=2, forward_extension_method=tangent, noise_filter_mode=model_v1. Legacy остаётся явным сравнительным режимом. Положительный interval 13–64 принят пользователем; прошлый tangent regression выполнен, здесь проверяется новая ROS интеграция.
- Вход: PointCloud2, finite XYZ/source frame, source header сохраняется. Viewer публикует исходные экспортированные XYZ как PointCloud2; отдельный node также принимает исходный ROS bag. Преобразование не выполняется: source <- source, assumed units/profile сохраняются.
- Контракты: raw CORE сохраняется; model negative не CLEAR; отсутствие axis/input → UNKNOWN с указанным mode; nearest reportable до source return. Header идентифицирует кадр; latency по monotonic/steady_clock.
- Allowed files: ROS2 node, CPU runtime/server/launcher/measurement wiring, интеграционные tests/scripts, этот task spec и run report. Model/core/geometry/config пороги не менять.
- Основная роль: текущий агент по lidar_obstacle_pipeline. Последовательно safety_geometry_reviewer (filter/output integration), затем validation_reviewer; независимость review не заявляется.
- Проверки: Humble Docker build; существующие unit/browser contracts; same-frame parity ROS model ↔ direct model по decisions/индексам/расстоянию на положительных/отрицательных кадрах; UNKNOWN/mismatched frame; source-frame switching; HTTP viewer result identity. Никакой новой калибровки и held-out quality claim.
- Acceptance: один model evaluator в C++ используется обоими entrypoints; launcher default даёт ROS2 transport/model_v1/tangent; положительные/отрицательные решения совпадают с frozen direct reference; negative paths fail closed; команды воспроизводимы.
- Validation target: L1 narrow tests, L3 только для фактически проверенной Docker → PointCloud2 → ROS2 node → HTTP viewer chain. Стенд, full 7-source replay и real-time не заявляются.
- Stop: несовпадение решений, неизвестный input contract или потребность изменить геометрию/модель; фиксировать evidence, не подбирать пороги.
- Артефакты: artefacts/stage_5/ros_model_v1_integration/. Результат: stage_5_ros_model_v1_integration_run.md.
