# CPU ROS2 → viewer: контракт результатов

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией. Каталог/контракт matching JSON переиспользуется, но прежний ROS transport и timings не описывают direct-плеер.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Дата: 2026-09-20. Режим: patch → safety-review → validation. Этап 4, шаг 4 плана.

- Goal: дать viewer все данные, уже вычисленные C++ CPU node для одного кадра: identity, CurveRailAxis, неизменённые bounds габарита и все source indices `CORE`; browser только рисует этот результат и не решает принадлежность точек габариту.
- Наблюдаемая проблема: текущий JSON node содержит status и ближайший source index, но не позволяет сопоставить результат с кадром или показать ось/все core-возвраты без повторного геометрического расчёта в JavaScript.
- Non-goals: новый viewer, ROS2 bag replay, видеофайл, новая геометрия/mesh membership, изменения CurveRailAxis, AutoRails, профиля/margins/thresholds, map, deskew, tracking, CUDA, метрики и semantic obstacle claim.
- Source of truth: `docs/README_work_plan.md` шаг 4, `docs/README_methodology.md` §§2, 6, 15, `curve_envelope_node.cpp`, `curve_envelope_core.hpp`, stage 3 result.
- ТЗ / этап: минимальная демонстрация показывает облако, обнаружение и расстояние; этап 4 — сигнализация на видео. Это только контракт для неё.
- Окружение: Ubuntu 22.04 + ROS 2 Humble + Docker; проверка — CPU Docker build и PointCloud2 smoke с saved `new_data` frame.
- Вход: один PointCloud2 в `hesai_lidar`, XYZ в `m_ASSUMED`, без TF/deskew/накопления. Transform: `hesai_lidar <- hesai_lidar` ASSUMED.
- Режим: candidate-only. Нет оси/невалидный input → `UNKNOWN`; status не становится `CLEAR`.
- Allowed files: `curve_envelope_node.cpp`, `tests/smoke_curve_envelope_node.py`, this spec/result and `docs/README_work_plan.md` only if status changes.
- Files to avoid: core membership arithmetic, C++/CUDA backend choice, profile/margin values, raw/bag, existing browser geometry and player.
- Защищённые контракты: source frame/timestamp сохраняются; indices относятся к исходному неизменённому point cloud; `CORE` includes all returns; bounds не меняются; ось не экстраполируется; viewer input carries `UNKNOWN` explicitly; никакого `CLEAR`/safety decision.
- Deliverables: C++ JSON fields for identity, pairs/axis, unchanged core/expanded bounds, all core indices and nearest XYZ; narrow smoke assertions.
- Reviewer: safety_geometry_reviewer, потому что result serialises safety-envelope membership; затем validation_reviewer. Оба последовательных прохода текущего агента, не независимые.
- Validation target: L1 for C++ Docker/ROS2 output schema on one development cloud and loss-of-support; L0 for viewer/video/bag quality.
- Acceptance: output identity matches received cloud; every core source index is valid and count equals `core_count`; axis has no extra support points; bounds equal active node parameters; UNKNOWN has no stale geometry/indices.
- Stop: source indices not from raw cloud, output needs new threshold/profile, unknown returns a negative/clear implication, or serialisation changes classification.
