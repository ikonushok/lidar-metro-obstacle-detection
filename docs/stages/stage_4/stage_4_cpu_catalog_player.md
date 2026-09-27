# C++ CPU catalog player

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией. Каталог/контракт matching JSON переиспользуется, но прежний ROS transport и timings не описывают direct-плеер.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Дата: 2026-09-20. Режим: patch → safety-review → validation. Этап 4, шаг 4 плана.

## Задача

- Goal: вернуть полный просмотр `new_data` в viewer, сохранив единственный вычислительный путь C++ CPU node для каждого показанного кадра, и дать воспроизводимый замер непрерывного диапазона.
- Наблюдаемая проблема: первоначальный CPU viewer содержал только три экспортированных кадра, поэтому не позволял листать весь движущийся набор или измерять скорость на последовательности.
- Non-goals: изменение CurveRailAxis, профиля/границ/порогов, deskew, карты, tracking, CUDA, классификация объектов, оценка TP/FP/FN и safety decision.
- Source of truth: `docs/README_work_plan.md`, `docs/methodology.md`, `dataset/for_hackathon/new_data`, C++ `curve_envelope_node` и его JSON contract.
- Этап: шаг 4 — предупреждения и расстояние в viewer; сквозной Docker → ROS2 result → viewer путь.
- Целевое окружение: Ubuntu 22.04 + ROS 2 Humble + Docker; фактическая проверка — Humble Docker image `lidar-mosmetro3d:stage-4-cpu-viewer`.
- Вход: `new_data` архив, `sensor_msgs/msg/PointCloud2`, метры; `hesai_lidar <- hesai_lidar`, без TF, deskew и накопления.
- Рабочие frames: C++ result и облако обязаны совпадать по `source_frame` и `header_timestamp_ns`; transform не применяется.
- Временная база: результат сопоставляется по header timestamp; wall latency измеряется `time.monotonic()` процесса вокруг отправки/получения ROS2.
- Allowed files: `scripts/cpu_catalog_runtime.py`, `scripts/serve_stage_2_cpu_catalog.py`, `scripts/measure_cpu_catalog_window.py`, `scripts/run_stage_2_cpu_player.ps1`, `scripts/export_cpu_viewer_replay.py`, `web/stage_4_cpu_viewer.html`, stage-4 docs, узкий тест launcher.
- Files to avoid: C++ CurveRailAxis/membership, geometry profile/bounds, ROS2 schemas, raw dataset and archive content, CUDA.
- Защищённые контракты: browser не вычисляет membership; C++ JSON — единственный источник статуса, core indices и distance; `UNKNOWN` не означает clear; lazy archive не экстраполирует данные и не создаёт кэш результата вне трёх кадров процесса.
- Deliverables: lazy manifest полного `new_data`, endpoint кадр+matching C++ JSON, CPU launcher, непрерывный measurement JSON, документация запуска.
- Путь отчёта: `docs/stages/stage_4/stage_4_cpu_catalog_player_run.md`.
- Основной агент: текущий агент по `agents/lidar_obstacle_pipeline.md`.
- Safety-review: требуется, поскольку viewer показывает safety envelope и предупреждение; проводится после реализации отдельным проходом текущего агента.
- Validation-review: требуется после safety-review для проверки evidence и границ claim; проводится отдельным проходом текущего агента.
- Validation target: L1 для 101 непрерывного development-window кадра и HTTP chain; L0 для WebGL manual playback, полного набора и требований реального времени.
- Acceptance criteria: manifest содержит весь архив; выбранный кадр получает raw XYZ и matching C++ JSON; C++ backend `cpu`; измерение записывает p50/p95 node и wall time; `UNKNOWN` не становится clear; launcher не ограничивает интервал тремя кадрами.
- Stop conditions: требуются изменения protected geometry/thresholds, browser добавляет новый детектор, C++ result не совпадает с raw frame или отсутствует подтверждение identity.
