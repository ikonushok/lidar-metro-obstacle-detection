# Наблюдаемые вторжения в габарит — результат

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией. Singleton/raw CORE не равен сигналу после model_v1.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Дата: 2026-09-20. Этап 3, шаг 3. Цель и границы: [task spec](stage_3_observed_intrusions.md).

## Что изменено

- C++ ROS2 node и browser-layer теперь явно называют каждый наблюдаемый возврат в поддержанном `CORE` габарите `OBSERVED_CORE_INTRUSION_CANDIDATE`. Размер компоненты не влияет на наличие предупреждения: низкий одиночный возврат сохранён.
- `MARGIN` остаётся отдельным результатом `OBSERVED_MARGIN_RETURN`; он не становится вторжением в `CORE`.
- JSON содержит `intrusion_candidate_present`, `margin_return_present`, ближайший source index и евклидово расстояние от `SOURCE_ORIGIN` в `m_ASSUMED`. При потере опоры они равны `null`, статус — `UNKNOWN`.
- Не изменялись пары рельсов, `CurveRailAxis`, профиль, margins, AutoRails thresholds, deskew, карта, tracking, семантический детектор или решение `CLEAR`.

## Evidence и выполненные команды

- `node --test tests/test_live_envelope.cjs tests/test_review_layers.cjs tests/test_player_playback.cjs` — **PASS, 21/21**. Покрыты границы, margin, низкий singleton, потеря геометрии, отсутствие `CLEAR` и текст предупреждения.
- `node --check web/stage_3_live_envelope.js` и `node --check web/stage_2_review_layers.js` — **PASS**.
- `docker build -t lidar-mosmetro3d:observed-intrusions-cpu -f Dockerfile .` — **PASS**. Собран ROS 2 Humble CPU image; `colcon build` завершён успешно.
- `docker run ... lidar-mosmetro3d:observed-intrusions-cpu python3 /app/tests/smoke_curve_envelope_node.py --xyzf /data/frame_01050.xyzf --backend cpu` — **PASS**. На сохранённом development-кадре `new_data`: `core_count=585`, `intrusion_candidate_present=true`, ближайший core return — `4.144 m` от source origin, `system_status=UNKNOWN`.
- Тот же smoke с `--expect-unknown` и единственным возвратом без пар рельсов — **PASS**: `reason=INSUFFICIENT_PAIRED_RAIL_SUPPORT`, `status=UNKNOWN`, оба поля присутствия равны `null`.
- `node scripts/replay_new_data_visual.cjs artefacts/stage_3/cuda_envelope/frames artefacts/stage_3/observed_intrusions` — **PASS**. На кадрах 1050, 1100 и 1150 все три результата — `OBSERVED_CORE_INTRUSION_CANDIDATE`; source mutations — 0. [Сводка replay](../../../artefacts/stage_3/observed_intrusions/visual_replay.json).

`FASTRTPS_DEFAULT_PROFILES_FILE` в обоих Docker smoke указывал на UDP-only профиль: это обход SHM Fast DDS, недоступного через Docker Desktop. Он не является проверкой полного bag replay.

## Safety-review

Последовательный safety-review текущим агентом, не независимый: **PASS_WITH_RISKS** для candidate-only режима.

- `CORE` вызывает предупреждение независимо от кластеризации; возвраты пола и рельсов не отбрасываются.
- Margin не подменяется core-вторжением. Потеря рельсовой опоры, невалидный input и отсутствие пересечений не дают `CLEAR`.
- Дальность явно обозначена как `SOURCE_ORIGIN`, не как пройденный путь, расстояние до объекта или калиброванная продольная дальность.
- Риск: габарит, frame и единицы остаются `ASSUMED`; наблюдаемые core-возвраты могут включать инфраструктуру. Это предупреждение-кандидат, не доказанный физический объект и не команда управления.

## Validation-review

Последовательный validation-review текущим агентом, не независимый: **PASS_WITH_RISKS, L1** для контракта на узких тестах, трёх development-кадрах и одном ROS2 PointCloud2 smoke.

Не проверены качество TP/FP/FN, разметка, реальный низкий объект на записи, полный поворот, длительный ROS2 bag replay, очередь/dropped frames, p95 полного pipeline и связь сдаваемого ROS2 output с viewer. JavaScript replay показывает `p95=282.2843 ms` только для локального JS AutoRails+check; это не замер C++ CPU pipeline и не claim real-time.

## Следующий минимальный шаг

Этап 4: сначала дополнить единственный JSON CPU ROS2 node полилинией оси, неизменёнными границами габарита и координатами ближайшего return; затем viewer отображает именно этот output на сохранённом replay без повторной независимой геометрической реализации. Проверить прямой участок, поворот, низкий кандидат и потерю опоры.
