# Покадровая кривая ось по опоре рельсов — план

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Дата: 2026-09-20. Режим: patch → safety-review → validation, этап 3.

- Goal: реализовать `CurveRailAxis` и sweep неизменённого reference-профиля по непрерывным парам, уже выбранным AutoRails в одном кадре.
- Наблюдаемая проблема: straight axis описывает только касательную короткого участка; на `new_data` её центр смещается по X. Вне поддержанного отрезка и при frame 1054 нужен `UNKNOWN`.
- Non-goals: новый детектор рельсов при `NO_STRAIGHT_CONSISTENT_PAIR`, изменение `geometry_new_data_experiment.yaml`, profile/margin/порогов AutoRails/группировки, TF/extrinsics, deskew, map/background, tracking, TTC, ROS2 и claims о качестве.
- Source of truth: `AGENTS.md`, `agents/context_router.md`, `agents/lidar_obstacle_pipeline.md`, [проверка геометрии](stage_3_new_data_geometry_review_run.md), [результат переноса](stage_3_new_data_transfer_run.md), методология §§5–6; фактические web-модули и узкие tests.
- Этап плана: этап 3, шаг «Кривая ось и габарит»; пользователь явно одобрил указанную минимальную спецификацию.
- Вход: raw finite XYZ в `hesai_lidar`; `rail_pairs` только из уже принятого AutoRails contiguous run. `hesai_lidar <- hesai_lidar`, X/-Y/Z и метры остаются ASSUMED.
- Изменяемые файлы: `web/stage_2_auto_rails.js`, `web/stage_2_review_layers.js`, `web/stage_3_live_envelope.js`, ближайшие Node tests, replay script при необходимости, этот план и отдельный отчёт. Артефакты: `artefacts/stage_3/curve_rail_axis/`.
- Не менять: raw/archive/bag, configs и numerical constants, baseline/Python, Docker/ROS2, labels и старые artefacts.
- Защищённые контракты: unchanged source bytes; нет скрытого straight fallback; до/после support или при недействительной геометрии — `UNKNOWN`; no `CLEAR`; low singleton остаётся кандидатом; никакого удаления rail/floor; timestamps не используются для movement/deskew.
- Реализация: AutoRails добавляет backward-compatible `rail_pairs`; `CurveRailAxis` строит ломаную из парных центров одного contiguous run и union сегментных призм. Пересечение принимается только на сегментах; до, после или в разрыве — `UNKNOWN`.
- Проверка: collinear equality со straight envelope; synthetic curved pairs; low/boundary singleton; missing/invalid/fragmented support; frame 1054; replay сохранённых 1050–1150 и существующие regression tests. Safety reviewer после diff, затем validation review того же агента без заявления независимости.
- Target: L1 для unit/integration и одного существующего saved development replay. Acceptance: перечисленные invariants проверены, old straight/manual flows регрессий не имеют, output явно маркирован ASSUMED/UNKNOWN.
- Stop: если curved axis расширяет область без конкретных пар, скрывает low return, меняет `UNKNOWN` в `CLEAR` или требует нового порога/калибровки — остановиться и оставить фичу выключенной.
