# Покадровая кривая ось по опоре рельсов — результат

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией. Singleton/raw CORE не равен сигналу после model_v1.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Дата: 2026-09-20. Этап 3, шаги 1–2 плана: кривая ось и габарит вдоль неё.

## Вывод

Реализован frame-local `CurveRailAxis`: ломаная проходит по центрам непрерывных пар рельсов одного кадра, а неизменённый reference-профиль образует объединение призм её сегментов. Нет экстраполяции за первую/последнюю пару и нет скрытого перехода на прямую ось: отсутствие двух поддержанных пар даёт `MISSING_CURVE_AXIS` и системный `UNKNOWN`.

Это устраняет геометрическую ошибку straight envelope в пределах уже найденной опоры, но не решает потерю AutoRails на выраженном повороте: новый детектор рельсов намеренно не входил в этот шаг. На сохранённом development-окне 1050–1150 frame 1054 остаётся `UNKNOWN`; это ожидаемое безопасное поведение.

## Изменения

- `web/stage_2_auto_rails.js`: успешный результат дополнен упорядоченными `rail_pairs`; исходные `rails`, опора и критерии выбора не изменены.
- `web/stage_2_review_layers.js`: добавлены `CurveRailAxis`, классификация и crop по объединению сегментных призм, визуализация ломаной и поперечников. Автоматический режим использует только `rail_pairs`; ручной прямой режим сохранён.
- `web/stage_3_live_envelope.js`: экспортирует статус и длину поддержанной кривой, а при её отсутствии — `MISSING_CURVE_AXIS`; `CLEAR` не добавлен.
- `scripts/replay_new_data_visual.cjs` и Node-тесты: используют кривую ось без straight fallback.

Не изменялись raw/bag, конфигурации, численные пороги, профиль, margin, TF/extrinsics, временная база, deskew, карта, tracking, TTC и ROS2-контракты.

## Evidence и команды

- [План](stage_3_curve_rail_axis_plan.md), [предыдущая проверка геометрии](stage_3_new_data_geometry_review_run.md), [перенос](stage_3_new_data_transfer_run.md).
- `node --check web/stage_2_auto_rails.js`, `web/stage_2_review_layers.js`, `web/stage_3_live_envelope.js`, `scripts/replay_new_data_visual.cjs` — успешно.
- `node --test tests/test_live_envelope.cjs tests/test_review_layers.cjs tests/test_player_playback.cjs` — 21 PASS. Есть проверки кривой, равенства прямому случаю, низкого singleton, границ, потери опоры и плеера.
- `node --test --test-name-pattern='automatic pair fits' tests/test_auto_rails.cjs` — 1 PASS.
- `node scripts/replay_new_data_visual.cjs artefacts/stage_3/new_data_transfer/baseline_1050_1150 artefacts/stage_3/curve_rail_axis` — 101 сохранённый development-кадр, исходный SHA-256 `3446edc7…75471`, `source_mutations: 0`.

В replay: 100 `CURVE_AXIS_SUPPORTED`, 1 `MISSING_CURVE_AXIS`; `straight_fallback_used: false` во всех кадрах. На 1050: 15 пар, 14 сегментов, 30.00 м опоры; на 1100: 13/12/23.60 м; на 1150: 10/9/17.76 м; на 1054 пар нет и результат — `UNKNOWN`. Артефакт: visual_replay.json: `../../../artefacts/stage_3/curve_rail_axis/visual_replay.json` — локальный артефакт недоступен; [восстановление](../../README_history.md#восстановление-недоступных-артефактов).

Полный `node --test tests/test_auto_rails.cjs`: 5 PASS, 1 FAIL. Падение UI lifecycle ожидает «Автоось» в пустом `auto-status`; оно уже зафиксировано в [результате переноса](stage_3_new_data_transfer_run.md) и не относится к вычислению оси. В рамках этой задачи его не исправляли.

## Safety-review

Проверка текущим агентом после реализации, не независимая. Вердикт: `PASS_WITH_RISKS` для заявленного исследовательского scope.

- Координаты остаются `hesai_lidar <- hesai_lidar`, X/-Y/Z и метры — `ASSUMED`; transform и timestamps не добавлялись.
- Профиль, margin и пороги не изменялись. Габарит существует только на сегментах из пар; до, после и без опоры возвращается `UNKNOWN`.
- Низкий singleton остаётся `CORE_INTERSECTION_CANDIDATE` независимо от минимального размера группы; rail/floor/background не удаляются.
- Кандидат пересечения не стал семантическим препятствием; системное решение остаётся `UNKNOWN`, `safety_decision_permitted: false`.

Остаточный риск: положение лидара, оси, единицы и профиль не калиброваны; инфраструктура по-прежнему попадает в кандидаты. Автоось формируется лишь из ранее принятого straight-consistent run и может отсутствовать на более сильном повороте.

## Validation review

Проверка текущим агентом, не независимая. Вердикт: `PASS_WITH_RISKS`, уровень `L1`.

Доказаны unit/integration-инварианты и один replay сохранённого development-окна. Не доказаны качество обнаружения, TP/FP/FN, поведение на размеченном повороте или низком реальном препятствии, real-time и независимое обобщение. Измеренные для этого Node replay `median 167.58 мс`, `p95 208.73 мс`, `max 256.95 мс` относятся только к локальному offline скрипту без I/O; это не latency системы и не claim real-time.

Следующий минимальный шаг: на размеченном сценарии или явно помеченной его недоступности проверить наблюдаемые вторжения внутри поддержанной кривой, отдельно для прямой, поворота, низкого препятствия и потери опоры; затем измерять ошибки, не менять пороги заранее.
