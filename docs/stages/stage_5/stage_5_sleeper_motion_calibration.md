# Калибровка движения `new_data` по шпалам — 2026-09-22

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Эксперимент/справка вне запуска direct_cpp+tangent+model_v1. Включение требует отдельной проверки эффекта и регрессии; результаты не меняют runtime default.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

## Задача

- Goal: проверить, можно ли использовать видимую периодичность шпал в начале `new_data` как локальную метрическую опору для оценки продольного межкадрового смещения.
- Наблюдаемая проблема: прямой ICP стен/свода недооценивает продольное движение в повторяющейся геометрии тоннеля; пользователь предложил привязку к шагу шпал на начальном участке.
- Non-goals: объявлять нормативный шаг шпал конкретного пути подтверждённым без наблюдаемой проверки; включать результат в deskew, карту, tracking, TTC, envelope или runtime.
- Source of truth: raw `new_data` PointCloud2, его bag timestamps, снимок кадра 0; user-authorized hypothesis о стандартном шаге; нормы пути — только как диапазон гипотез, не как proof конкретного метро.
- Этап: 5 — калибровка/проверка движения.
- Вход и время: `hesai_lidar`, raw source XYZ, bag timestamps одной записи. Header/per-point clocks не используются. Направление `s=-Y` — наблюдаемая гипотеза только для probe.
- Калибровочная гипотеза: начальный прямой участок имеет pitch 1/1840 км = 0,543478 м; известны и другие нормы 0,500 м и метро-диапазон 1680–2000 шпал/км, поэтому pitch должен быть проверен по видимому сигналу и не переносится на весь маршрут автоматически.
- Метод: построить 1D signal поперечных элементов в зоне рельс/шпал; оценить period и межкадровый phase shift, сохранить все конкурирующие correlation peaks. При скоростях выше одного pitch на кадр result имеет целочисленную alias-неоднозначность.
- Allowed files: этот отчёт, offline scripts, artefacts stage 5, README после положительной проверки.
- Files to avoid: active detector, profile/margins, ROS2 schemas, source bags, runtime config.
- Защищённые контракты: неподтверждённая phase-оценка не заменяет odometry и не публикуется как actual speed; alias/quality failures дают `UNKNOWN`.
- Основной агент: lidar_obstacle_pipeline; safety-review не нужен, production geometry не меняется. Validation проход анализирует evidence и границы claim.
- Validation target: L1 для initial sleeper probe; отдельный L1 для full sequence возможен только если phase и unwrapping имеют проверяемую опору.
- Acceptance: signal имеет устойчивый подтверждаемый pitch, межкадровая корреляция даёт не-aliased displacement или явно показывает неоднозначность.
- Stop conditions: прямой участок не подтверждает pitch, преобладает aliasing, либо для выбора integer pitch нужна внешняя скорость/метка.

## Отчёт о завершении

- Что изменено: создан `scripts/probe_new_data_sleeper_phase.py`; выполнены три raw-only probes первых 101 кадров `new_data` и сохранены JSON в `artefacts/stage_5/`.
- Evidence inspected: raw frame 0 (XY/XZ/YZ projection), 101 исходное PointCloud2 из первых частей `new_data`, bag timestamps, source-frame XYZ. Проверены доступные нормы: для путей метрополитена описан диапазон 1680–2000 шпал/км, поэтому нет единственного «стандартного» pitch без документации конкретного пути.
- Commands run:
  - `docker run ... probe_new_data_sleeper_phase.py ... new_data_sleeper_phase_probe_2026-09-22.json` — PASS, raw return-density signal.
  - То же с `z=[-1.5,-1.2]` и `z=[-1.2,-0.9]` — PASS, two narrow vertical bands.
  - То же с occupancy-by-lateral-cell signal — PASS, suppressing repeated returns per cell.
- Результаты: user-provided hypothesis 1840 шпал/км соответствует 0,543478 м. Однако dominant autocorrelation period в full/low/high bands равен 0,410/0,610/0,400 м соответственно; occupancy signal также даёт 0,400 м. Сигнал не подтверждает единый pitch 0,543478 м и может содержать rail/scan sampling structure. Для `pitch=0,543478 м` соседние correlation peaks дают alias increment около 19,58 км/ч на frame interval; фазовый shift не определяет целую часть числа пройденных шпал.
- Validation level achieved: L1 для bounded initial raw probe. Verdict: **BLOCK** для автоматической калибровки скорости/пути по «стандартному» шагу шпал; **PASS_WITH_RISKS** только для вывода, что в начальном облаке есть периодические поперечные структуры, но их метрический смысл не установлен.
- Что не проверено: фактическая эпюра конкретного метрополитеновского пути, ручная геометрическая идентификация шпал, association одной и той же шпалы между frames, initial speed/acceleration и integer-pitch unwrapping.
- Известные FP/FN или safety-риски: выбор 0,5 или 0,543478 м без evidence создаст систематическую scale error; выбор nearest correlation peak способен дать скорость, ошибающуюся на кратные около 19,58 км/ч. Никакой output не используется в runtime/deskew/TTC/envelope.
- Следующий минимальный тест: предоставить паспортную эпюру данного пути или вручную отметить минимум три последовательные шпалы в frame 0 и одну идентифицируемую путевую метку/шпалу в последующем frame; затем проверить pitch и integer displacement на размеченном коротком интервале до запуска full trajectory.
- Residual risk: даже подтверждённый pitch сам по себе не устраняет periodic aliasing при движении более одного pitch за frame; для полной покадровой скорости требуется non-periodic landmark либо validated velocity/acceleration prior.
