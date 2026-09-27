# C++ ядро оси и пересечения с габаритом — результат

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Дата: 2026-09-20. Этап 3. Цель и границы: [task spec](stage_3_cpp_envelope_core.md).

## Изменено

- Добавлены C++ реализации `AutoRails` и frame-local CurveRailAxis envelope: `src/cpp/auto_rails_core.*`, `src/cpp/curve_envelope_core.*`.
- Геометрия сохраняет текущий метод: пары рельсов одного кадра → ломаная сегментов → existing reference profile и margins → `CORE`, `MARGIN`, `OUTSIDE_REFERENCE` или `UNKNOWN`. Нет экстраполяции, straight fallback, ground/rail removal, карты, deskew, tracking и `CLEAR`.
- Добавлен ROS2 Humble пакет `lidar_mosmetro3d_cpp` с node `curve_envelope_node`: PointCloud2 XYZ float32 → AutoRails → C++ envelope → JSON в `/stage_3/curve_envelope_candidate`. Он требует `source_frame=hesai_lidar`, выдаёт `UNKNOWN` для неподдержанного frame/schema/endianness/осей и публикует только candidate statuses с `safety_decision_permitted=false`.
- Dockerfile собирает пакет через colcon. Значения профиля и margins передаются параметрами node с прежними экспериментальными defaults; они по-прежнему ASSUMED и не являются калибровкой.
- Добавлены CLI и скрипты только для parity/benchmark evidence. Они не участвуют в runtime node и не изменяют исходный XYZ.

## Проверки и evidence

1. C++ unit test: низкий singleton → CORE, margin/outside/unknown distinct, пустая опора → все UNKNOWN, одиночная невалидная пара отвергается.
2. AutoRails C++ сверена с JS на saved new_data frames 1050, 1100, 1150: точные численные значения всех пар рельсов совпали. При первой проверке кадр 1150 дал 11 вместо 10 пар; отсутствовавшая проверка residual была добавлена, после чего все три кадра совпали. Эта находка не скрыта как успешный первый результат.
3. C++ labels побайтно совпали с JS для всех точек кадров 1050, 1100, 1150; также совпали core/margin/outside/unknown и source index ближайших core/margin точек. Исходные XYZ не менялись.
4. В Ubuntu 22.04 Docker: `g++ -std=c++17 -O3 -Wall -Wextra -Werror` собрал core, CLI и test; `colcon build` собрал ROS2 package. Полный Dockerfile собран как `lidar-mosmetro3d:cpp-curve-core`; `ros2 pkg executables lidar_mosmetro3d_cpp` видит `curve_envelope_node`.
5. [Benchmark](../../../artefacts/stage_3/cpp_envelope_core/benchmark.json): среднее C++ AutoRails + envelope ядро 8.00–10.40 мс на кадрах 1050/1054/1100/1150 при 30 повторениях. Это вычислительное ядро без PointCloud2 decoding, ROS2 publish, bag I/O и viewer rendering; не является full-pipeline latency или доказательством real-time на стенде ТЗ.

## Safety-review

Sequential safety-review текущим агентом после diff, не независимое. **PASS_WITH_RISKS для ASSUMED, frame-local candidate-only режима.**

- `hesai_lidar <- hesai_lidar`, XYZ и метры остаются ASSUMED. Node не переименовывает frame: несовпадение header.frame_id даёт `UNKNOWN`.
- Отсутствие AutoRails, одна пара, невалидные bounds/schema или endianness не превращаются в отсутствие помехи: node выдаёт `UNKNOWN`. Для saved frame 1054 C++ kernel: 0 pairs, 189984 UNKNOWN, без core/margin.
- Low returns не фильтруются и candidate status не зависит от min cluster points; расстояние остаётся евклидовым до исходной ближайшей точки от source origin. Нет output `CLEAR` и нет команды управления.
- Не проверены physical profile, margin, frame/extrinsics, real low obstacle, полный поворот, TF/deskew, ложные тревоги и подлинная дальность. Инфраструктура может быть candidate, как и в JS reference.

## Validation и ограничения

Validation-проход текущим агентом: **L1** для C++ unit/parity и bounded offline kernel benchmark; **L0** для ROS2 node runtime, кроме успешной сборки/обнаружения executable. Новая node не была подтверждена bag replay. Отдельный `ros2 topic echo` в Docker Desktop сначала не смог создать Fast DDS shared-memory transport; повтор в одном контейнере с UDP-only smoke-профилем дошёл до `ros2 bag play`, но вход `dataset/for_hackathon/new_data` оказался 90-ГиБ архивом, а не распакованным rosbag storage directory: rosbag2 не нашёл storage plugin. Архив намеренно не распаковывался. Это не ошибка алгоритма и не доказательство runtime.

Выполненные команды:

- `node scripts/export_curve_envelope_pairs.cjs ...` и `node scripts/export_curve_envelope_labels.cjs ...` на трёх кадрах;
- `node scripts/compare_auto_rail_pairs.cjs ...` — 3 exact numeric PASS;
- `docker run ... g++ ... test_curve_envelope_core ... curve_pipeline_cli ...` — compile/unit/Pipeline benchmark PASS;
- `docker run ... colcon build ...` — package build PASS;
- `docker build -t lidar-mosmetro3d:cpp-curve-core .` — Dockerfile build PASS;
- `docker run --rm lidar-mosmetro3d:cpp-curve-core ros2 pkg executables lidar_mosmetro3d_cpp` — executable visible.

Не закрыты: end-to-end bag replay, p95 полного node, очередь/dropped frames, CPU/RAM, viewer consuming exactly C++ output, actual quality TP/FP/FN и video. Следующий минимальный тест — один контейнерный ROS2 launch/replay/collector с корректной DDS transport configuration, затем длинный прогон 1× с измерением p95, queue и drops. Включать C++ output в видео только после этой проверки.
