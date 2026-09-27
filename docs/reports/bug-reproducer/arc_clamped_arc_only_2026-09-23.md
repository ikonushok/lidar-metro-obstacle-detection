# Arc-only continuation — 2026-09-23

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Исторический отчёт/исследование; команды, режим и результаты относятся к описанной ниже проверке, не ко всей текущей версии.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../../stages/stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

## Цель

Убрать смешение методов в `arc_clamped`: путь строится принятой дугой либо заканчивается на observed rail-pairs. Касательная не используется как скрытый fallback.

## Воспроизведение

В `tests/test_curve_envelope_core.cpp` тест вызывает `ExtendRailPairsForwardArcClamped` с радиусом ниже `min_radius_m`. Предыдущая реализация возвращала `ARC_CLAMPED_FALLBACK_TANGENT` и synthetic pair. Тест падал: **REPRODUCED**.

## Исправление

- добавлен `ARC_CLAMPED_REJECTED`;
- при недостаточных данных, невалидном fit или малом радиусе остаются только observed pairs;
- принятая дуга остаётся одним arc-path и сохраняет ширину пары;
- `tangent` и `arc_limited` не менялись.

## Проверки

| Проверка | Результат |
|---|---|
| C++ regression, red → green | PASS |
| Docker Humble build | PASS |
| ROS2 `curve_envelope_node` smoke, arc_clamped | PASS |
| `roundT_pressureGate_roundT` 132/136/229, arc 53 м | APPLIED, конец 80 м |
| `doubleT_obstacle` 13/64 | FN: препятствие не найдено |
| `doubleT_obstacle` 145/185 | нет срабатывания |

## Safety-review текущим агентом

**PASS_WITH_RISKS.** При отказе модели пути дальняя synthetic geometry не создаётся; пространство после observed конца не покрывается габаритом, а candidate-only `system_status` остаётся `UNKNOWN`. Полный arc-path в текущей калибровке ухудшает обнаружение известной помехи, поэтому не является default.

## Уровень валидации

L3 для реализации и прямого replay указанных кадров. Не выполнены полный post-change replay всех записей и независимая разметка углов пути.

## Runtime status

`tangent` остаётся единственным рабочим default. `arc_clamped` — экспериментальный режим калибровки геометрии; он не должен включаться для production, пока не сохраняет известную помеху `doubleT_obstacle` на кадрах 13 и 64.

## Следующий минимальный тест

Разделить calibration-сценарии кривого пути и `doubleT_obstacle`; подобрать горизонт и ограничение угла по целому набору без смены default до сохранения known obstacle.
