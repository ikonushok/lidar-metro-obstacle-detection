# Повторная development-проверка Stage 3 baseline

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Дата: 2026-09-20. Режим: validation.

## Задача

- Goal: повторно выполнить актуальные узкие Node-тесты и full replay существующих visual Stage 3 веток на неизменённом export `doubleT_obstacle`.
- Claim: только candidate/`UNKNOWN`-поведение, source-buffer immutability и identity; не обнаружение человека, не свободный путь и не safety decision.
- Non-goals: менять ручные anchors, geometry contract, детектор, пороги, ROS2-код, исходные XYZ или labels.
- Source of truth: `docs/README_work_plan.md` (этап 3), `docs/stages/stage_3/stage_3_envelope_baseline.md`, `config/geometry_contract.yaml`, manifest/xyzf и текущие тесты.
- Вход: один development export `doubleT_obstacle`, 201 кадров, source `lidar_livox`, XYZ без transform; единицы и ось — `ASSUMED`.
- Защищённые контракты: `UNKNOWN != CLEAR`; `safety_decision_permitted=false`; no ground/rail/background suppression; raw source buffers неизменны; разметка не передаётся в детектор.
- Allowed files: этот отчёт и перезаписываемые существующими replay-скриптами artifacts в `artefacts/stage_3/live_envelope/` и `artefacts/stage_3/obstacle_membership/`.
- Validation: `node --test ...`; `node tests/replay_live_envelope.cjs --all`; `node tests/replay_obstacle_membership.cjs`.
- Target evidence: L1 для текущих Node replay contracts; не выше L1, поскольку нет нового ROS2/Docker end-to-end и независимого test run.
- Stop conditions: при ошибке теста не менять код/пороги автоматически; зафиксировать failure и остановиться.

## Результат

- `node --test tests/test_live_envelope.cjs tests/test_auto_rails.cjs tests/test_review_layers.cjs tests/test_object_candidates.cjs tests/test_raw_player.cjs tests/test_player_playback.cjs` — 29/29 PASS.
- `node tests/replay_live_envelope.cjs --all` — 201/201 кадров; source buffers changed: 0; core candidates: 201/201; group limit: 0. Параметры остаются `ASSUMED`; результат каждого кадра — `CORE_INTERSECTION_CANDIDATE`, а system status — `UNKNOWN`. Локальное Node измерение auto-axis + checker: median 48.103 мс, p95 61.502 мс, max 131.214 мс; это не ROS2/UI/real-time claim.
- `node tests/replay_obstacle_membership.cjs` — 201 кадров; source buffers changed: 0; component observations: `CORE_INTERSECTION` 3962, `MARGIN_INTERSECTION` 550, `UNKNOWN` 1575, `OBSERVED_RETURNS_OUTSIDE` 1. Две development anchors (`OBS-002`, `OBS-003`) принадлежат своим observed components, но обе находятся вне поддержанного interval auto-axis и остаются `UNKNOWN`; event recall и FP/мин не вычислялись.

Артефакты обновлены существующими replay-скриптами: `artefacts/stage_3/live_envelope/development_full_replay.json` и `artefacts/stage_3/obstacle_membership/coverage.json`.

## Validation verdict

`PASS_WITH_RISKS`, L1 для текущих Node contracts и одного development export. Baseline вычисляет и сохраняет candidate/`UNKNOWN` согласованно, но 201/201 core candidates не доказывают наличие 201 препятствия и не дают quality metrics. Независимый test run, валидная геометрия пути, event visibility intervals, FP/мин, ROS2 runtime и эксплуатационная безопасность остаются непроверенными.

Следующий минимальный шаг этапа 4: разметить не рельсы, а один короткий **чистый** временной интервал и границы видимости одного из двух уже отмеченных объектов. Это позволит впервые посчитать development candidate rate/мин и coverage события без изменения детектора.
