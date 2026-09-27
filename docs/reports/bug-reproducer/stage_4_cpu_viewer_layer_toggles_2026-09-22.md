# Stage 4 CPU Viewer Layer Toggles

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Исторический отчёт/исследование; команды, режим и результаты относятся к описанной ниже проверке, не ко всей текущей версии. Каталог/контракт matching JSON переиспользуется, но прежний ROS transport и timings не описывают direct-плеер.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../../stages/stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Date: 2026-09-22

Result: `FIX_PROVEN` for the inspected Stage 4 viewer layer controls.

## Problem

The UI exposed one combined envelope checkbox and reused the `margin-layer` checkbox for both yellow margin points and the expanded warning boundary. This made it impossible to independently hide/show the train envelope `core` boundary and the external `core +0.5 m` warning boundary.

The checkbox `Контрольные помехи, отметки и измерения` was also not useful for the current inspection flow and confused the layer controls with manual review annotations.

## Fix

- Removed the `Контрольные помехи, отметки и измерения` layer checkbox from the Stage 4 panel.
- Added `Габарит поезда core` for the white core boundary.
- Added `Граница ближней зоны +0,5 м` for the expanded warning boundary.
- Kept `Точки внутри габарита core` and `Точки между core и ближней зоной` as point-color controls.
- Left C++ geometry, membership, `core`, `expanded`, and the `+0.5 m` margin unchanged.

## Evidence

Initial reproducer:

```text
node --test tests/test_cpu_viewer_envelope_geometry.cjs
FAILED: viewer can toggle core and expanded envelope boundaries independently
```

Fixed checks:

```text
node --test tests/test_cpu_viewer_envelope_geometry.cjs
PASS: 3/3

node --check web/stage_4_cpu_player.js
PASS

node --check web/stage_4_cpu_player_controls.js
PASS

node --test tests/test_player_playback.cjs
PASS: 4/4
```

Live `localhost:8099` check:

- `marks-layer` absent.
- `train-layer` absent.
- `core-envelope-layer` present and checked.
- `margin-envelope-layer` present and checked.
- Turning off `margin-envelope-layer` leaves `core-envelope-layer`, `core-layer`, and `margin-layer` unchanged.
- Frame was restored to `156`.

## Limitation

`tests.test_stage_4_all_sources_contract` was not run: `python` was unavailable in the current shell, `.venv` pointed to a missing Python executable, and `py -3` reported no installed Python.
