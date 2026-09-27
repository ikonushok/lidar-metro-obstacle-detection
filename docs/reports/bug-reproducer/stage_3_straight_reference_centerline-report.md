# Bug-reproducer — дрейф сетки и габарита

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Исторический отчёт/исследование; команды, режим и результаты относятся к описанной ниже проверке, не ко всей текущей версии.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../../stages/stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

## Итог

`FIX_UNVERIFIED`: регрессионный тест перешёл из red в green, а узкие
UI-проверки проходят. Реальный браузерный replay с пересобранными assets ещё
не выполнен.

## Reproduction

Пользователь предоставил кадры, где облако туннеля выглядит прямым, а сетка и
train sweep имеют общий боковой уход. Созданный `tests/test_player_rail_centerline.cjs`
проверил production source: до фикса отсутствовала прямая reference-ось, а
`renderAutoGradePath`, `renderReferenceProfile` и `renderFloorGrid` использовали
`ACTIVE_ASSUMED_AUTO_TRACK`.

Команда `node --test tests/test_player_rail_centerline.cjs` до фикса завершилась
FAIL с ожидаемым сообщением об отсутствии `straightRailCenterline`.

## Root cause и исправление

`ACTIVE_ASSUMED_AUTO_TRACK` строится от `FLOOR_UNDER_RAILS_ASSUMED`, поэтому
не является центром рельсов. `web/stage_2_player.html` теперь задаёт прямую
reference-ось из `visualization_overlay` и использует её для зелёной линии,
сетки и обоих габаритов. Детектор не изменён.

## Green checks

- `node --test tests/test_player_rail_centerline.cjs tests/test_player_path_stability.cjs` — 5/5 PASS;
- `node tests/test_player_floor.cjs` — PASS;
- `python.exe -m unittest tests.test_stage_2_player_ui -v` — 1/1 PASS;
- inline JavaScript syntax — PASS;
- `git diff --check` — exit 0.

## Остаточный риск

Ось остаётся `UNCONFIRMED` визуальной гипотезой; это не калибровка и не
распознавание рельсов. Candidate-геометрия Stage 3 не менялась. Для проверки
отображения требуется повторный export и ручной просмотр кадров в браузере.
