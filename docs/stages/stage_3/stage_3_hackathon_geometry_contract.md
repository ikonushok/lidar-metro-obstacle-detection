# Этап 3 — demo-геометрический контракт

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

## Спецификация

- Goal: снять блокер реализации baseline через явно ограниченный `ASSUMED_HACKATHON` контракт, не выдавая safety-решение.
- Наблюдаемая проблема или исходный claim: внешний калибровочный пакет не предоставлен; пользователь одобрил проектные допущения, которые будут заменены перед production.
- Non-goals: подтверждение калибровки, `CLEAR/NO_OBSTACLE`, safety case, deskew, карта, tracking, оценка TP/FP/FN или активация профиля для `hesai_lidar`.
- Source of truth: ТЗ §§2–3, 3.3; `docs/work_plan.md` этап 3; `docs/dataset_audit.md`; `docs/methodology.md`; `config/geometry_contract.yaml`.
- Этап: 3.
- Входные данные и единицы: `doubleT_obstacle`, frame `lidar_livox`; метры, -Y вперёд и identity transform — только `ASSUMED_HACKATHON`.
- Рабочие frames и направление transforms: `hackathon_track_lidar_livox <- lidar_livox`; identity является demo-допущением.
- Режим: candidate-only envelope-only. Отсутствие кандидата — `UNKNOWN`; возможный кандидат — `OBSTACLE_CANDIDATE_ASSUMED_GEOMETRY`; `CLEAR` и safety-decision запрещены.
- Allowed files: `config/geometry_contract.yaml`, `docs/train_clearance.md`, `docs/methodology.md`, `tests/test_geometry_contract.py`, этот отчёт.
- Files to avoid: исходные bag/TAR, ROS message/QoS contracts, детекторные численные пороги, production profile.
- Защищённые контракты: `DEGRADED/UNKNOWN` не является `CLEAR`; transform указан как `target <- source`; demo-профиль действует только для `lidar_livox`; production требует `VERIFIED` evidence.
- Safety reviewer: требуется, так как изменены frame, extrinsics, путь, профиль и margin.
- Validation reviewer: после safety-review, проверяет YAML и тесты; target L1 для статического demo-контракта, L0 для его физических свойств.
- Validation method: YAML parse; unit-tests инвариантов demo/production; полный current unit-suite в Humble Docker image.
- Acceptance criteria: все допущения, scope и production replacement evidence записаны; candidate разрешён, `CLEAR`/safety запрещены; `hesai_lidar` остаётся `UNKNOWN`.
- Stop conditions: не менять статус на `VERIFIED`, не включать `geometric_decision_enabled`, не добавлять незафиксированные пороги или профили.

## Отчёт о завершении

- Что изменено: `config/geometry_contract.yaml` переведён в ограниченный `ASSUMED_HACKATHON` профиль для `lidar_livox`; записаны метрические оси, identity `hackathon_track_lidar_livox <- lidar_livox`, straight path вдоль `-Y`, прямоугольник 2.8 × 3.7 m и margin 0.20 m. Добавлены запреты `CLEAR`/safety-decision, статус `UNKNOWN` при отсутствии кандидата и production replacement evidence. Обновлены `docs/train_clearance.md`, `docs/methodology.md` и unit-test YAML-инвариантов.
- Evidence inspected: `AGENTS.md`; `agents/context_router.md`; `agents/lidar_obstacle_pipeline.md`; `agents/safety_geometry_reviewer.md`; `agents/validation_reviewer.md`; ТЗ §§2–3; `docs/dataset_audit.md`; `docs/work_plan.md`; текущие config/source/tests.
- Commands run и результаты:
  - `docker build --progress plain -t lidar-mosmetro3d:stage_3_geometry .` — `FAILED`: `.dockerignore` разрешает только `src/`, `scripts/`, `tests/`, `config/`, но Dockerfile содержит `COPY web/ /app/web/`.
  - `docker run --rm --mount "type=bind,source=$PWD,target=/verify,readonly" lidar-mosmetro3d:stage_2 python3 -m unittest discover -s /verify/tests -p test_geometry_contract.py -v` — 3/3 `OK` после финального изменения YAML.
  - `docker run --rm --mount "type=bind,source=$PWD,target=/verify,readonly" -e PYTHONPATH=/verify/src lidar-mosmetro3d:stage_2 python3 -m unittest discover -s /verify/tests -v` — 12/13 `OK`; единственное падение: существующий `test_gates_follow_reference_cross_section` использует строгое float-сравнение.
- Safety-review текущим агентом: `PASS_WITH_RISKS` для demo-контракта. Инварианты: transform обозначен как `target <- source`; identity, оси, метры, path, профиль и margin имеют статус `ASSUMED_HACKATHON`; активен только `lidar_livox`; candidate разрешён, но `geometric_decision_enabled`, `safety_decision_permitted` и `clear_decision_permitted` равны `false`; no-candidate result равен `UNKNOWN`. Это последовательный проход текущего агента, не независимое внешнее review.
- Validation-review текущим агентом: `PASS_WITH_RISKS`, L1 для структуры и исполнимых YAML-инвариантов в Humble image; L0 для физических свойств допущений. Новый контракт прошёл 3/3; полный current suite не зелёный из-за несвязанного float-теста, а чистая current-image сборка дополнительно блокирована build context.
- Что не проверено: точность допущений; `hesai_lidar`; границы envelope/низкое препятствие; фактический ROS2 consumer, distance, clustering, replay и метрики; чистая сборка текущего source tree.
- Известные FP/FN или safety-риски: приближённые параметры могут дать ложный candidate или пропуск; отсутствие candidate не даёт `CLEAR`. Demo-профиль не является калибровкой и не пригоден для production.
- Следующий минимальный тест: отдельным изменением исправить Docker build context, затем реализовать и проверить ROS2 consumer на `lidar_livox` с no-candidate -> `UNKNOWN` и candidate -> маркированным demo-результатом.
- Residual risk: до внешней калибровки и event labels система может демонстрировать только техническую гипотезу, а не safety/quality claim.
