# Автоматический профиль уклона пути — Stage 3

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

## Задача

- Goal: автоматически оценивать локальный вертикальный профиль пути из LiDAR и использовать его как дополнительную candidate-only envelope hypothesis на дальности 0–200 м.
- Наблюдаемая проблема: на визуализации `doubleT_obstacle` путь уходит под уклон; горизонтальный assumed envelope может не пересечь дальнюю геометрию, хотя облако содержит визуальный кандидат.
- Non-goals: `CLEAR`, safety decision, production-калибровка, suppression статичной инфраструктуры, map/tracking/deskew и изменение TF/единиц.
- Source of truth: пользовательское визуальное наблюдение, `config/geometry_contract.yaml`, `docs/methodology.md` §§21–22.
- Вход: active `lidar_livox`, assumed метры и ось `−Y`; profile estimate строится отдельно для каждого кадра.
- Frames/transforms: `hackathon_track_lidar_livox <- lidar_livox`, identity, `ASSUMED_HACKATHON`.
- Режим: auto-grade envelope объединяется с текущим прямым assumed envelope, поэтому успешная оценка может только добавлять candidates, а не убирать baseline candidates. При недостаточной оценке auto-grade не создаёт `CLEAR`; исходный no-candidate остаётся `UNKNOWN`.
- Allowed files: `config/geometry_contract.yaml`, `src/stage_3_baseline.py`, `tests/test_stage_3_baseline.py`, player presentation, этот файл.
- Protected contracts: candidate-only; `UNKNOWN != CLEAR`; направление transform; raw frame/timestamp; никакого исключения rail/ground/visual-static объектов.
- Validation target: L1 unit + replay; L0 для физической корректности автоматического профиля.
- Acceptance: валидный synthetic incline добавляет candidate на наклонном path; горизонтальные candidates не теряются; невалидная оценка не даёт `CLEAR`; результат содержит diagnostics profile estimate.
- Stop conditions: не подавлять точки, не объявлять профиль/дальность verified, не менять margin или статусы в safety decision.

## Отчёт о завершении

- Что изменено: добавлен `auto_grade_path` со support surface `FLOOR_UNDER_RAILS_ASSUMED`. В каждом кадре lower floor profile оценивается по 10-процентному квантилю Z в бинах 0–60 м; допустимый fit формирует линейный `z(−Y)` и добавляет auto-grade envelope к прямому fallback envelope. Точки не подавляются.
- Evidence inspected: один кадр `doubleT_obstacle` показал плотную floor support поверхность в пределах X −1.8…1.8 м; визуальный просмотр пользователя показал уклон пути и потенциальную дальнюю помеху.
- Commands run: container build; unit suite 35/35; ROS2 replay `doubleT_obstacle` на rate 0.25 — 201 expected / 201 received, decode errors 0, timeout false, player exit 0, 91.45 s.
- Runtime result: auto profile `ACTIVE_ASSUMED_AUTO_GRADE` в 201/201 кадре; 18 864 кластеров пересекли auto-grade hypothesis; максимальная дальность записанного candidate 172.38 м. Это не метрика качества и не доказательство препятствия.
- Визуализация: статический reference profile был смещён примерно на 1.79 м выше floor support. Плеер теперь сдвигает его нижнюю грань к текущему auto-profile, поэтому показываемый профиль соответствует candidate volume от опоры пола/рельсов до верхней границы; это консервативная визуальная гипотеза, не измеренный профиль колёс.
- Плоскость grid в плеере автоматически наклоняется и сдвигается по тому же `z(−Y)`, чтобы не создавать визуальную иллюзию горизонтального пола при активном авто-профиле.
- Safety review текущим агентом: `PASS_WITH_RISKS`. Auto-grade объединён с straight fallback, поэтому не убирает baseline candidates. При недостатке floor support auto estimate получает `UNKNOWN_*`; отсутствие кандидата остаётся `UNKNOWN`, без `CLEAR`. Риск ложных candidates высок: floor/rail identification, оси, единицы и профиль поезда не верифицированы.
- Residual risk: автоматически извлечённый профиль остаётся хакатонной геометрической гипотезой и не может заменить подтверждённый профиль/калибровку Заказчика. До этого дальние визуальные объекты нельзя классифицировать как безопасные.
- Следующий минимальный тест: визуально проверить бирюзовую линию профиля на кадрах 0, 100 и 200 и отметить, покрывает ли она рельсовое основание; затем измерить candidates в диапазонах 0–40, 40–100, 100–200 м.
