# C++-ядро пересечения с кривым габаритом

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Дата: 2026-09-20. Режим: patch → safety-review → validation, этап 3.

- Goal: перенести вычислительные ядра AutoRails и «исходная точка → сегменты CurveRailAxis → зона и ближайшая точка» в C++ для будущего ROS2-пайплайна.
- Наблюдаемая проблема: JS-проверка габарита занимает 124–187 мс на реальных кадрах с осью; поиск рельсов занимает 27–32 мс, построение оси около 0.05 мс. Узкое место создаёт промежуточные объекты для пар точка×сегмент.
- Non-goals: изменение профиля, margin, численных порогов, группировки, TF/extrinsics, deskew, карты, tracking, QoS или safety decision.
- Source of truth: `web/stage_2_review_layers.js`, `web/stage_3_live_envelope.js`, `tests/test_live_envelope.cjs`, `stage_3_curve_rail_axis_plan.md`, ТЗ §3.3 и §8.3.
- Этап плана: этап 3, ускорение вычислительного ядра без изменения геометрического метода.
- Целевое окружение: Ubuntu 22.04 + ROS 2 Humble + Docker; фактическая проверка — `g++` Ubuntu 22.04 внутри существующего Docker image.
- Вход: конечные raw XYZ, `rail_pairs` одного contiguous run, reference profile и existing margins. Рабочий frame `hesai_lidar <- hesai_lidar`; XYZ и метры остаются ASSUMED.
- Данные: сохранённое development-окно new_data 1050–1150. Нет утверждения о качестве или калибровке.
- Режим: покадровый envelope-only. Нет оси или нет сегмента под точкой — `UNKNOWN`; нет пересечений на поддержанном участке не становится `CLEAR`.
- Временная база: не используется. Производительность измеряется монотонными часами процесса, только для вычислительного ядра.
- Allowed files: `src/cpp/curve_envelope_core.*`, `src/cpp/curve_envelope_cli.cpp`, `src/cpp/curve_pipeline_cli.cpp`, `src/cpp/auto_rails_core.*`, `src/cpp/auto_rails_cli.cpp`, `src/lidar_mosmetro3d_cpp/**`, `Dockerfile`, `tests/test_curve_envelope_core.cpp`, `scripts/export_curve_envelope_pairs.cjs`, `scripts/export_curve_envelope_labels.cjs`, `scripts/compare_auto_rail_pairs.cjs`, документация этапа и новые `artefacts/stage_3/cpp_envelope_core/`.
- Files to avoid: JS-реализация, profile/config, ROS2 interfaces, Dockerfile, raw/bag, пороги и прежние артефакты.
- Защищённые контракты: first matching CORE, затем MARGIN, затем OUTSIDE_REFERENCE, `UNKNOWN` без поддержанного сегмента; низкие одиночные точки сохраняются; расстояние — евклидово от source origin; без `CLEAR` и без удаления rail/floor.
- Deliverables: C++ core, CLI для реальных XYZ/pairs, тесты boundary/low/unknown, сравнение с JS replay и speed evidence.
- Основной агент: текущий. Safety-review требуется после diff, так как код реализует membership/safety envelope. Затем validation проход текущего агента по parity и runtime evidence; это не независимые review.
- Validation target: L1 для unit tests и bounded replay, L0 для будущей ROS2-интеграции.
- Acceptance: результат C++ равен JS по зонам, счётчикам и ближайшей core/margin точке на synthetic tests и saved development window; нет `CLEAR`; код компилируется в Ubuntu container; указан measured time.
- Stop conditions: любое расхождение зон/nearest, невалидная опора, скрытое расширение области, изменение `UNKNOWN` или потребность в новом пороге — остановить перенос и не подключать к runtime.
