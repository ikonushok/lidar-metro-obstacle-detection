# Локальная 3D-полилиния пути — Stage 3

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

## Задача

- Goal: дополнить прямую/линейную гипотезу пути локальной 3D-полилинией по последовательным участкам floor/rail support, чтобы candidate-only envelope мог следовать за уклоном, переломом уклона и поворотом в плане.
- Наблюдаемая проблема: единая прямая `z(-Y)` не описывает спуск с последующим подъёмом; фиксированная ось `-Y` не описывает поворот рельсов.
- Non-goals: подтверждение фактических рельсов, `CLEAR`, safety decision, suppression инфраструктуры, map/tracking/deskew, изменение TF, единиц, margin или профиля вагона.
- Source of truth: визуальное наблюдение пользователя, `docs/methodology.md` §6.1, `config/geometry_contract.yaml` и код Stage 3.
- Этап: 3. Режим — `ASSUMED_HACKATHON`, candidate-only.
- Вход: `lidar_livox`, метры; `hackathon_track_lidar_livox <- lidar_livox`; начальное направление `-Y` — только fallback.
- Метод: в каждом 10-метровом bin выбирается нижняя floor support полоса в адаптивном lateral gate. Её медиана X и низкий квантиль Z образуют опорную точку. Между валидными точками строится локальный 3D sweep габарита.
- Fallback: итоговая область — объединение local-track, auto-grade и straight envelope. Ни одна существующая candidate-точка не удаляется.
- Allowed files: `config/geometry_contract.yaml`, `src/stage_3_baseline.py`, `web/stage_2_player.html`, соответствующие тесты и этот отчёт.
- Protected contracts: `UNKNOWN != CLEAR`; raw frame/timestamp; никаких ground/rail/static suppression; transform и единицы не меняются.
- Нужен safety review: да, затрагивается траектория и envelope. После реализации — проход текущим агентом с негативными сценариями.
- Validation target: L1 (synthetic tests + контейнерная проверка); L0 физической достоверности rail extraction.
- Acceptance: synthetic S-уклон и поворот добавляют local-track candidate; straight/auto-grade candidates не теряются; недостаток support не даёт `CLEAR`; player показывает полилинию и grid-ribbon по ней.
- Stop conditions: не выдавать estimate за verified rail geometry, не использовать его для suppression или safety decision.

## Отчёт о завершении

- Что изменено: добавлен `auto_track_path`. Он собирает локальные опорные точки `depth, X, Z` из нижней floor support полосы в адаптивном lateral gate и строит sweep assumed train profile между соседними точками. Плеер показывает эту траекторию бирюзовой линией, а прежнюю бесконечную grid plane заменяет grid-ribbon вдоль полилинии. Для auto-grade fallback отображается прежняя наклонная плоскость.
- Evidence inspected: `docs/methodology.md` §6.1 требует sweep по центральной линии только при доступной геометрии пути; код Stage 3 и текущий replay. В 201/201 результатах записаны `path_profiles.auto_track` и `path_profiles.auto_grade` со статусом `ACTIVE_*`.
- Commands run: контейнерная сборка; полный unit suite — 36/36 passed; ROS2 replay `doubleT_obstacle` на rate 0.15 — 201 expected / 201 received / difference 0 / decode errors 0 / player exit 0 / timeout false / 146.56 s. Предыдущий replay на rate 0.25 потерял 15 кадров при p95 processing около 551 ms и поэтому не заменил основной файл результатов.
- Validation level achieved: L1 для алгоритмического контракта. Synthetic test покрывает поворот, спуск с последующим подъёмом и сохранение straight fallback. Реальный replay доказывает доставку результатов, но не физическую точность пути.
- Safety review текущим агентом: PASS_WITH_RISKS. Local-track, auto-grade и straight fallback объединяются; новая гипотеза не подавляет точки и не создаёт `CLEAR`. При недостатке support local-track становится `UNKNOWN_*`, а straight/grade fallback остаются candidate-only.
- Что не проверено: опорные точки не доказывают положение головок рельсов; они могут следовать полу, шпалам или другой штатной геометрии. Нет независимой траектории, ground truth поворота или production-калибровки.
- Известные FP/FN или safety-риски: union сохраняет старую прямую область и поэтому может добавлять FP на кривой. Неверная floor support гипотеза может создать лишний local-track candidate; она не должна трактоваться как verified путь или safety decision.
- Следующий минимальный тест: в плеере проверить кадры до, на и после визуального перелома/поворота: cyan line и grid-ribbon должны проходить по наблюдаемому рельсовому основанию. Затем сравнить candidate rate по range bands на неизменной конфигурации.
- Residual risk: для production нужен подтверждённый centreline/rail model от Заказчика либо независимая оценка рельсов с измеримой ошибкой; текущая реализация остаётся `ASSUMED_HACKATHON`.
