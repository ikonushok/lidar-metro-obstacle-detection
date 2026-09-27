# CPU result viewer

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией. Каталог/контракт matching JSON переиспользуется, но прежний ROS transport и timings не описывают direct-плеер.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Дата: 2026-09-20. Режим: patch → safety-review → validation. Этап 4, шаг 4 плана.

- Goal: создать воспроизводимый статический viewer для исходных XYZ и JSON одного CPU ROS2 node; viewer подсвечивает полученные `core_source_indices`, показывает CurveRailAxis, core bounds, candidate-warning и ближайшее расстояние.
- Наблюдаемая проблема: CPU JSON готов для viewer, но не существовало связки, которая сохраняет matching raw frames и эти результаты без запуска другого JS-детектора.
- Non-goals: видеофайл, новый алгоритм, повторный membership расчёт в browser, изменение Axis/profile/margins/AutoRails, CUDA, deskew/map/tracking/semantic classification, full bag или качества TP/FP/FN.
- Source of truth: `docs/README_work_plan.md` шаг 4, `stage_4_cpu_viewer_contract.md`, CPU `curve_envelope_node`, saved `new_data` frames 1050/1100/1150.
- Среда: Ubuntu 22.04 + ROS 2 Humble + Docker. Input: source XYZ, `hesai_lidar <- hesai_lidar`, `m_ASSUMED`; no TF, deskew or accumulation.
- Allowed files: `scripts/export_cpu_viewer_replay.py`, `scripts/run_stage_4_cpu_viewer.ps1`, `scripts/run_stage_2_cpu_player.ps1`, `web/stage_4_cpu_viewer.html`, stage-4 docs, narrow validation only.
- Files to avoid: CurveRailAxis/core membership, C++ thresholds/profile/bounds, CUDA, raw archives/bags, existing player geometry.
- Защищённые контракты: exporter sends only CPU node result; header/source frame match before writing; all returned core indices remain source indices; no geometry/membership calculation changes status; `UNKNOWN` never means clear.
- Deliverables: static HTML, Three.js assets, raw XYZ and manifest/results exported by CPU ROS2; warning and distance from result JSON.
- Review: safety_geometry_reviewer then validation_reviewer as sequential current-agent passes, not independent.
- Validation target: L1 for three saved development frames and HTTP integrity; L0 for visual manual inspection, video and bag replay.
- Acceptance: manifest/result identity match; result count equals raw frame count; all core indexes exist in raw frame; viewer source contains no AutoRails/live-envelope/membership code; `UNKNOWN` displays no free-path conclusion.
- Stop: viewer computes a different geometry or core label, an identity mismatch is accepted, a protected parameter must change, or a clear conclusion is exposed.
