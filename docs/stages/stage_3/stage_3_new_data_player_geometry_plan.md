# Экспериментальная геометрия new_data в плеере — план

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Дата: 2026-09-20. Режим: patch → safety-review → validation, этап 3.

- Goal: включить в каталожном плеере отображение уже реализованных `CurveRailAxis` и габарита для `new_data`.
- Наблюдаемая проблема: каталог принудительно публикует `geometry_enabled: false` и не передаёт profile/оси, хотя их frame-local эксперимент уже реализован и проверен на saved replay.
- Non-goals: изменение AutoRails, `CurveRailAxis`, profile/margin/порогов, raw TAR/bag, deskew, map/background, tracking, TTC, ROS2 и claims о качестве или безопасности.
- Source of truth: `AGENTS.md`, `agents/context_router.md`, `agents/lidar_obstacle_pipeline.md`, `config/geometry_new_data_experiment.yaml`, [результат кривой оси](stage_3_curve_rail_axis_run.md), каталожный сервер и UI.
- Этап плана: этап 3, после шагов «CurveRailAxis» и «Габарит вдоль оси»; пользователь явно запросил включение отображения.
- Вход: lazy archive `new_data`, frame `hesai_lidar`, source XYZ. Оси, единицы, вынос лидара и profile остаются `ASSUMED_HACKATHON`.
- Allowed files: `scripts/serve_stage_2_catalog.py`, `web/stage_2_raw_player.html`, ближайшие tests, этот план и отчёт; артефакты — `artefacts/stage_3/new_data_player_geometry/`.
- Files to avoid: raw/archive, `geometry_new_data_experiment.yaml`, numerical configs, geometry/ROS2 runtime, old player manifests и stage-3 results.
- Защищённые контракты: `UNKNOWN != CLEAR`; `safety_decision_permitted=false`; AutoRails без пар не даёт прямой fallback; geometry only frame-local; никаких map/deskew/timestamp claims; raw bytes не меняются.
- Реализация: каталог читает только разрешённые поля имеющегося experimental config и публикует их как `visualization_overlay`, `geometry_enabled: true`, статус и видимое предупреждение. UI показывает предупреждение независимо от включённости geometry.
- Deliverables: ось, опоры, reference envelope и пересечения текущего габарита — experimental candidate layers; margin/crop/group frames — пользовательские diagnostic layers; карта, deskew, tracking, TTC — не включать.
- Safety reviewer: нужен, потому что включается отображение safety envelope; затем validation review текущим агентом без заявления независимости.
- Target: L1 — manifest contract, UI test/replay одного кадра с осью и кадра без оси.
- Stop: если UI может показать `CLEAR`, скрывает warning/UNKNOWN, меняет geometry config или требует полный анализ TAR — отключить geometry и зафиксировать blocker.
