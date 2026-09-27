# Stage 3 — прямая reference-ось в плеере

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

## Задача

- Goal: устранить визуальный боковой дрейф сетки и габаритов в Stage 2 player;
  добавить общую зелёную ось, с которой совпадают сетка и два габарита.
- Наблюдаемая проблема: на предоставленных пользователем кадрах облако туннеля
  визуально прямое, а сетка и фиолетовые sweep уходят в сторону.
- Source of truth: `config/geometry_contract.yaml` задаёт только
  `ASSUMED_HACKATHON` straight reference (`X=0`, `forward=-Y`); результаты
  `auto_track_path` имеют `support_surface: FLOOR_UNDER_RAILS_ASSUMED` и не
  являются распознанными рельсами.
- Этап: Stage 3, визуальная интеграция геометрии.
- Non-goals: не менять `stage_3_baseline.py`, candidate-зоны, пороги,
  safety-envelope, TF, калибровку или решение детектора.
- Allowed files: `web/stage_2_player.html`, узкие UI-тесты и этот отчёт.
- Защищённые контракты: `UNKNOWN` не становится `CLEAR`; reference остаётся
  `UNCONFIRMED`, `safety_decision_permitted=false`; автоматическая гипотеза
  пола не называется распознаванием рельсов.

## Изменение

Добавлена `straightRailCenterline(overlay)`: два узла от `forward_start_m` до
`forward_end_m` с `x=track_centerline_lateral_m`, `y=-depth`,
`z=rail_head_vertical_m`. Зелёная линия, `buildTrackGrid` и оба sweep габарита
используют этот единственный reference path. HUD явно сообщает, что это
неподтверждённая визуальная гипотеза, не rail detection и не safety decision.

## Evidence и проверки

- До исправления: `node --test tests/test_player_rail_centerline.cjs` — FAIL:
  отсутствовала straight rail reference; функции выбирали
  `ACTIVE_ASSUMED_AUTO_TRACK`.
- После исправления:
  - `node --test tests/test_player_rail_centerline.cjs tests/test_player_path_stability.cjs` — 5/5 PASS;
  - `node tests/test_player_floor.cjs` — PASS;
  - `python.exe -m unittest tests.test_stage_2_player_ui -v` — 1/1 PASS;
  - проверка компиляции inline JavaScript через `new Function(script)` — PASS;
  - `git diff --check` — exit 0; выведены только предупреждения CRLF для
    других файлов рабочего дерева.

## Safety-review (проход текущего агента)

Verdict: PASS_WITH_RISKS. Изменён только browser overlay; вызовы детектора и
его данные не изменены. Новый reference остаётся UNCONFIRMED, не разрешает
`CLEAR`, не скрывает точек и не подавляет низкие препятствия. Блокирующий риск:
это прямой reference из config, а не измеренная ось рельсов; визуальное
совпадение не доказывает физическую калибровку и не исправляет candidate ROI
Stage 3, который продолжает использовать assumed auto-track union.

## Validation

Достигнут L1 для статически проверенной визуальной привязки. Реальный browser
replay после export не выполнялся; требуется заново экспортировать web asset и
визуально проверить предоставленные кадры. Следующий минимальный тест:
`./scripts/run_stage_2_player.ps1 -RebuildData`, затем убедиться, что зелёная
линия, сетка и оба фиолетовых габарита совпадают по прямой оси в ракурсе
"Сверху".
