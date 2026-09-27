# Дальность Stage 3 baseline — 200 м

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Эксперимент/справка вне запуска direct_cpp+tangent+model_v1. Включение требует отдельной проверки эффекта и регрессии; результаты не меняют runtime default.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

## Задача

- Goal: расширить assumed ROI Stage 3 с 40 до 200 м по оси пути `−Y` для хакатонного просмотра `doubleT_obstacle`.
- Основание: подготовленные 201 кадров содержат возвраты до 209.04 м по `−Y` (p95 208.89 м); лимит 40 м исключал большую часть доступной дальности.
- Non-goals: не подтверждать дальность лидара, не менять единицы/оси/TF, профиль, margins, пороги кластеров либо статус candidate-only.
- Allowed files: `config/geometry_contract.yaml` и этот отчёт.
- Защищённые контракты: `ASSUMED_HACKATHON`; никаких `CLEAR`/safety decisions.
- Validation target: L1 — загрузка конфигурации и unit suite; end-to-end replay отдельно.

## Отчёт о завершении

- Что изменено: `visualization_overlay.forward_end_m`, `path.valid_forward_range_m` и `detection.roi.forward_max_m` согласованно изменены на 200 м.
- Evidence inspected: измерение всех 201 подготовленных кадров `doubleT_obstacle`: max `−Y` 209.04 м, p95 208.89 м.
- Residual risk: 200 м — согласованное хакатонное допущение, а не верифицированная рабочая дальность или доказательство качества детекции на каждом диапазоне.
- Следующий минимальный тест: rebuild/replay и раздельная оценка кандидатов по distance bands.
