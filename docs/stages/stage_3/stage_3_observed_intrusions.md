# Наблюдаемые вторжения в поддержанный габарит

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией. Singleton/raw CORE не равен сигналу после model_v1.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Дата: 2026-09-20. Режим: patch → safety-review → validation. Этап 3, шаг 3 плана.

- Goal: явным выходом помечать каждый наблюдаемый возврат в core габарита как `OBSERVED_CORE_INTRUSION_CANDIDATE`, сохранить ближайшую исходную точку и дать UI немедленный candidate-warning.
- Наблюдаемая проблема: текущие zone labels уже сохраняют все core returns, включая низкий singleton, но JSON и UI называют их только «геометрическими пересечениями», что не фиксирует требуемый контракт сигнализации «всё внутри габарита — помеха-кандидат».
- Non-goals: семантическая классификация, подтверждение физического препятствия, изменение CurveRailAxis/AutoRails, profile/margins/thresholds, clustering, исключение рельсов/пола, TF/extrinsics, deskew, карта, tracking, TTC, `CLEAR`, видео и качество TP/FP/FN.
- Source of truth: `docs/README_work_plan.md` шаг 3, `docs/README_methodology.md`, C++ CurveRailAxis core, `web/stage_3_live_envelope.js`, текущие tests и stage_3_curve_rail_axis_run.md.
- Целевое окружение: Ubuntu 22.04 + ROS 2 Humble + Docker; узкие UI tests и C++ package build доступны локально.
- Вход/frames: source XYZ, `hesai_lidar <- hesai_lidar`, метры ASSUMED; один current frame без accumulation. Bag/header/per-point timestamps не участвуют.
- Объекты решения: `core_count>0` означает `intrusion_candidate_present=true`; margin returns остаются отдельным warning-layer observation и не превращаются в core intrusion. Нет оси/unsupported segment/invalid input → `UNKNOWN`, а не отсутствие помехи.
- Allowed files: `src/lidar_mosmetro3d_cpp/src/curve_envelope_node.cpp`, `web/stage_3_live_envelope.js`, `web/stage_2_review_layers.js`, `Dockerfile.cuda`, `scripts/ros_entrypoint.sh`, ближайшие Node tests, C++ package test/smoke evidence, this spec/result and `artefacts/stage_3/observed_intrusions/`.
- Files to avoid: profile/config values, AutoRails/CurveRailAxis/core membership arithmetic, raw/bag, map/deskew/tracking, object-component thresholds and final video pipeline.
- Защищённые контракты: same source indices/zone labels/nearest distance; core low singleton is immediate; margin is not core; UNKNOWN never becomes `CLEAR`; `system_status=UNKNOWN` and `safety_decision_permitted=false` remain.
- Deliverables: namespaced candidate fields in C++ JSON and viewer summary, UI warning text, narrow tests for core/margin/low/unknown, build and bounded replay evidence.
- Reviewer: `safety_geometry_reviewer` after implementation because output describes envelope intrusion; validation pass follows. Both are sequential passes by the current agent, not independent review.
- Validation target: L1 for contract tests plus saved development frames; L0 for ROS2 bag-to-viewer and semantic obstacle quality.
- Acceptance: every core label produces candidate presence regardless of component size; nearest core is a source return in metres; margin-only and missing support do not assert core intrusion; no protected geometry or parameter changes.
- Stop conditions: a core return is lost, a margin is raised to core, a missing segment produces a negative result, or a change requires tuning an existing threshold.
