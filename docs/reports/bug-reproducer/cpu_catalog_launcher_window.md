# CPU catalog launcher: двухкадровый/трёхкадровый регресс

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Исторический отчёт/исследование; команды, режим и результаты относятся к описанной ниже проверке, не ко всей текущей версии.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../../stages/stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Дата: 2026-09-20. Категория: bug-reproducer. Статус: **FIX_PROVEN** в границах проверки ниже.

## Цель

Доказать и исправить регресс: новый C++ launcher ограничивал viewer жёстко заданными кадрами и не позволял проверять скорость на непрерывном участке.

## Evidence и воспроизведение

- Изучены `scripts/run_stage_2_cpu_player.ps1`, `scripts/export_cpu_viewer_replay.py`, старый lazy catalog и C++ viewer contract.
- До исправления source-level test обнаруживал отсутствующие `FirstIndex`/`LastIndex` и defaults 1050/1150.
- Red command: `docker run --rm -e PYTHONDONTWRITEBYTECODE=1 --mount type=bind,source=<project>,target=/verify,readonly lidar-mosmetro3d:stage-4-cpu-viewer python3 /verify/tests/test_run_stage_2_cpu_player.py -v` — FAIL до изменения.

## Исправление и green evidence

- Launcher принимает `-FirstIndex`, `-LastIndex` и `-Measure`; полный catalog больше не экспортирует заранее фиксированное число кадров.
- Exporter больше не содержит defaults 1050/1150.
- Тот же test после исправления — PASS, 2 tests.
- Сквозной HTTP manifest содержит 11 271 кадров; измеритель успешно обработал 1050–1150 и сохранил p50/p95.

## Ограничение

Тест доказывает контракт launcher и сквозной диапазон 101 кадр, но не ручной WebGL rendering, не полные 11 271 кадров и не production throughput.
