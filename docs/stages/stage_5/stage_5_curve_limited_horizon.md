# Криволинейное продолжение оси с ограниченным горизонтом — спецификация

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Эксперимент/справка вне запуска direct_cpp+tangent+model_v1. Включение требует отдельной проверки эффекта и регрессии; результаты не меняют runtime default.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Дата: 2026-09-23. Режим: patch → safety-review → validation. Этап 5.

## Задача

- Goal: исправить документацию о фактической forward tangent extrapolation и добавить выбираемый кандидат `arc_limited` для продолжения CurveRailAxis по дуге только на явно заданный ограниченный горизонт.
- Наблюдаемая проблема: текущая C++ ветка строит ломаную по наблюдаемым рельсам, но затем добавляет одну синтетическую пару на `rail_forward_max_m` вдоль последней касательной. На повороте дальний габарит снова становится прямым.
- Non-goals: изменение profile/margins, frames, TF, units, timestamps, deskew, рельсовых порогов, CUDA, QoS, background, tracking, критериев core/margin/UNKNOWN, default-режима или safety decision.
- Source of truth: `src/cpp/curve_envelope_core.*`, `src/lidar_mosmetro3d_cpp/src/curve_envelope_node.cpp`, matching stream CLI/runtime, tests и `docs/README_work_plan.md`.
- Пункт ТЗ и обязательный результат: контейнерный candidate-only envelope baseline; `UNKNOWN` не означает свободный путь.
- Этап docs/work_plan.md: 5, адресное улучшение геометрии после наблюдаемой опоры.
- Целевое окружение: Ubuntu 22.04 + ROS 2 Humble + Docker; фактическая проверка — existing Docker image and narrow C++/ROS smoke.
- Входные данные и единицы: один `PointCloud2` с finite XYZ, `hesai_lidar <- hesai_lidar`, X/-Y/Z и m остаются `ASSUMED_HACKATHON`.
- Конкретный вход: synthetic C++ cases и saved development frame 1054 для ROS smoke; без новых bag/replay claims.
- Рабочие frames и transforms: source identity only; новый код не вводит transform.
- Режим: `forward_extension_method=tangent` сохраняется default. `arc_limited` использует только последние три наблюдаемые центры пар; horizon передаётся явным параметром. При нулевом/невалидном горизонте, недостаточной или коллинеарной опоре continuation не добавляется, точки вне observed segments остаются `UNKNOWN`.
- Временная база: не используется; вычислительная задержка не является deliverable этого изменения.
- Allowed files: C++ envelope core/node/stream CLI, CPU runtime/launcher при необходимости передачи параметров, ближайшие tests, `docs/README_work_plan.md`, этот spec и отдельный run report.
- Files to avoid: geometry profile/config constants, ROS schemas/QoS, raw bags, CUDA implementation, calibration/test splits.
- Защищённые контракты: observed rail pairs не меняются; no hidden fallback; core returns не подавляются; `UNKNOWN != CLEAR`; default tangent behavior остаётся byte-compatible по смыслу; arc continuation маркируется synthetic and candidate-only.
- Deliverables: documented current tangent extension; selectable `arc_limited`; JSON diagnostics method/horizon/status; narrow geometric and node smoke checks; safety then validation report.
- Путь отчёта: `docs/stages/stage_5/stage_5_curve_limited_horizon_run.md`.
- Основной агент: lidar obstacle pipeline.
- Safety reviewer: требуется, так как изменяется envelope beyond observed support.
- Validation reviewer: после safety-review, тем же агентом отдельным проходом без заявления независимости.
- Validation target: L1 for C++ unit and JSON contract; L3 only if existing Humble ROS smoke completes for a saved frame.
- Validation method: curve/straight/invalid-support unit cases; compile; ROS smoke in both tangent default and explicit arc mode.
- Acceptance criteria: tangent default unchanged; valid arc endpoint follows last observed three-center circle and never exceeds explicit horizon or `rail_forward_max_m`; invalid arc does not fall back to tangent; outputs expose extension basis; negative inputs remain `UNKNOWN`.
- Stop conditions: need to alter profile/margin/thresholds/frames, make arc default, or rely on temporal accumulation/deskew.
