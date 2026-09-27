# CPU ROS2 → viewer: контракт результатов — результат

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией. Каталог/контракт matching JSON переиспользуется, но прежний ROS transport и timings не описывают direct-плеер.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Дата: 2026-09-20. Этап 4. Цель и границы: [task spec](stage_4_cpu_viewer_contract.md).

## Что изменено

- `curve_envelope_node` сохраняет identity полученного `PointCloud2`: `header_timestamp_ns` и `source_frame`.
- Для поддержанной оси JSON содержит полилинию центров rail pairs, исходные left/right пары, неизменённые `CORE` и `MARGIN` bounds, все `core_source_indices` и координаты ближайшего core return.
- Индексы относятся к полному исходному облаку, которое node не меняет. Поэтому viewer может подсветить все core returns без собственного membership-расчёта.
- При `MISSING_CURVE_AXIS` поля геометрии пусты или `null`, `core_source_indices=[]`, candidate fields равны `null`; stale geometry не переносится на следующий кадр.

## Evidence и команды

- `docker build -t lidar-mosmetro3d:stage-4-cpu-contract -f Dockerfile .` — **PASS**: ROS 2 Humble C++ package собран в CPU-only image.
- `docker run ... lidar-mosmetro3d:stage-4-cpu-contract python3 /app/tests/smoke_curve_envelope_node.py --xyzf /data/frame_01050.xyzf --backend cpu` — **PASS**. На saved `new_data` frame 1050 получены `rail_pair_count=15`, `core_count=585`, 585 core indices, полилиния из 15 points, source identity и координаты ближайшего return; active bounds совпали с `[-1.4, 1.4, 0.0, 3.7]` и `[-1.9, 1.9, -0.5, 4.2]`.
- Тот же smoke с `--expect-unknown` — **PASS**: один возврат не поддержал rail pairs, output получил `MISSING_CURVE_AXIS`, пустые axis/pairs/indices и `null` bounds/candidate fields.

## Safety-review

Последовательный safety-review текущим агентом, не независимый: **PASS_WITH_RISKS**.

- Менялась только сериализация уже принятого CPU результата; CurveRailAxis, membership, profile, margins, thresholds и backend остались прежними.
- Каждый serialised core index соответствует labels исходного кадра; тест проверяет равенство числа indices `core_count` и включение nearest core index.
- `UNKNOWN` не несёт геометрию прошлого кадра и не превращается в `CLEAR`.
- Риск: `m_ASSUMED`, frame и профиль остаются непроверенной геометрической гипотезой; JSON payload, QoS и задержка его доставки на длительном потоке ещё не измерены.

## Validation-review

Последовательный validation-review текущим агентом, не независимый: **PASS_WITH_RISKS, L1** для формата C++ output на одном реальном saved development cloud и негативном сценарии потери опоры.

Не проверены viewer, video, ROS2 bag replay, matching identity на реальном header timestamp, скорость сериализации, queue/dropped frames, прямой/поворот/низкое реальное препятствие и качество TP/FP/FN. CUDA в этой проверке не используется.

## Следующий минимальный шаг

Сделать adapter viewer, который принимает этот JSON и соответствующий неизменённый raw frame, подсвечивает `core_source_indices`, рисует полученную axis/bounds и выводит status/nearest distance. После этого проверить четыре сценария на replay.
