# Stage 5 — сравнительный эксперимент оси пути и пересечений габарита

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Эксперимент/справка вне запуска direct_cpp+tangent+model_v1. Включение требует отдельной проверки эффекта и регрессии; результаты не меняют runtime default.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

## Задача

- Goal: на фиксированном development-наборе одиночных LiDAR-кадров проверить, улучшает ли один открытый метод криволинейное восстановление оси относительно текущего AutoRails без изменения рабочего детектора.
- Наблюдаемая проблема или исходный claim: C++ `DetectAutoRails` и браузерный `AutoRails.detect` отбирают пары рельсов глобальной линейной моделью по станциям; последующая `CurveRailAxis`/C++ envelope строит ломаную по наблюдённым парам. На повороте линейный inlier gate способен сделать корректную локальную опору `UNKNOWN` либо исказить её выбор.
- Non-goals: смена runtime, ROS2-интерфейсов, профиля, margin, frames, TF, timestamps, фоновой карты, семантической фильтрации, GPU и накопления кадров.
- Source of truth: ТЗ; `AGENTS.md`; `docs/README_{work_plan,methodology,dataset_audit}.md`; текущий C++/JS/Python код, конфиги, сохранённые облака и выполненные команды. Старый отчёт об открытых средствах — только источник гипотез.
- Пункт/раздел ТЗ и обязательный результат: baseline для препятствия/расстояния/diagnostics; обязательная среда в дальнейшем Ubuntu 22.04 + ROS 2 Humble + Docker. Настоящий offline-experiment не является runtime-подтверждением.
- Этап docs/work_plan.md: этап 5 — измерение геометрии и улучшения после baseline.
- Целевое окружение: Ubuntu 22.04 + ROS 2 Humble + Docker; фактическая среда проверки: локальная Windows workspace, offline CLI/Node/Python; контейнер не меняется и не заявляется проверенным этим экспериментом.
- Входные данные и единицы: сохранённые `*.xyzf` с float32 XYZ в метрах; рабочая конвенция существующего AutoRails: x — поперечная, s = -y — вперёд, z — вертикаль. Transform не применяется; геометрия остаётся `working_lidar_frame <- source_lidar_frame` identity только как допущение текущего локального offline-режима.
- Конкретный набор: будет создан явный manifest с кадрами прямой, поворота, разреженной дальней опоры, потери рельсов и доступными low/infrastructure in/out-envelope. Неразмеченные либо отсутствующие случаи не будут выдумываться; синтетика — отдельная группа.
- Факты/непроверенные допущения: по аудиту проверены только выборки облаков, TF/odom/IMU не подтверждены. Нельзя делать multi-frame fusion или объявлять ручные сечения абсолютной калибровкой.
- Режим baseline/расширений: оба метода получают один исходный кадр; один и тот же неизменённый профиль и единую реализацию проверки пересечений. При недостаточной опоре — `UNKNOWN`, не `CLEAR`.
- Временная база: измеряется только вычислительное время `time.perf_counter_ns()`/монотонные часы процесса вокруг offline алгоритма; I/O, ROS decoding/publish и viewer исключены и будут указаны.
- Allowed files: `docs/stages/stage_5/`, `scripts/`, `tests/`, `artefacts/stage_5/`; только экспериментальные файлы.
- Files to avoid: основной C++ ROS2 node, действующие YAML профиля/порогов, сообщения, launch, production detector и исходные облака.
- Защищённые контракты: смысл любого измеренного пересечения — препятствие независимо от класса/повторяемости/карты; profile/margin/coordinate/time contracts; `UNKNOWN != CLEAR`.
- Deliverables: task spec (создан); dataset manifest; проверка применимости `GISLab-ELTE/railroad`; один альтернативный метод либо доказанное ограничение; парный результат, safety-review, validation-review и воспроизводимый отчёт.
- Путь отчёта: этот файл; сырые CSV/JSON/визуализации — `artefacts/stage_5/`.
- Основной агент: текущий агент по `agents/lidar_obstacle_pipeline.md`.
- Нужен ли `safety_geometry_reviewer`: да, после эксперимента — затронуты ось/envelope classification, хотя runtime не меняется.
- Нужен ли `validation_reviewer`: да, после safety-review; проходы выполняет тот же агент последовательно и не являются независимыми.
- Validation target: L1 для изолированного offline-experiment; L0 для runtime-пакета.
- Validation method: статические тесты и парный запуск на manifest; ручная проверка сохранённых сечений доступным измерительным инструментом; проверка инвариантов low/single-return/infrastructure; фиксированные версии и команды.
- Acceptance criteria: кандидат не изменяет входные точки/профиль/margin, не превращает отсутствие поддержки в `CLEAR`, даёт сравнимую ось на тех же опорах; рекомендация основана на ошибке относительно явно ограниченных ручных отметок, длине подтверждённой поддержки, `UNKNOWN`, пересечениях и времени. При недостаточной разметке не считать precision/recall/FP.
- Stop conditions: не установить/не тащить тяжёлую библиотеку, если `railroad` требует MLS-плотности, LAS/LAZ либо multiple scans, недоступные одиночным кадрам; не вносить в runtime неподтверждённый кандидат.

## Отчёт о завершении

### Что изменено

- Созданы только изолированные `scripts/stage_5_rail_axis_experiment.cjs`, его узкий тест и новые `artefacts/stage_5/`.
- Runtime, C++ ROS2-node, профили, margin, пороги, frames, TF, часы, карту и исходные данные не менялись. Runtime автоматически не переключался.
- Baseline: неизменённый `AutoRails.detect` — global linear consensus пар рельсов, затем неизменённые `CurveRailAxis` и `live-envelope`.
- Кандидат: локальный dynamic-programming path только по тем же station/ridge/pair eligibility. Связь допускает лишь соседнюю согласованную пару, ограничена `maxGap`/`maxSlope`, не экстраполирует и при отсутствии пути остаётся `UNKNOWN`. Это экспериментальный минимальный fallback, а не изменение открытого runtime.

### Установленный текущий путь

`src/cpp/auto_rails_core.cpp` строит линейные `l(s), r(s), lz(s), rz(s)`, собирает только inlier-строки этой модели и возвращает `best.rows`. Браузерный `web/stage_2_auto_rails.js` реализует тот же global linear consensus. В то же время `web/stage_2_review_layers.js::curveRailAxis` и `src/cpp/curve_envelope_core.cpp::BuildSegments` строят сегменты ломаной по уже отобранным `rail_pairs`; C++ `curve_envelope_node` всегда вызывает `DetectAutoRails` перед этим sweep.

Следовательно, гипотеза подтверждена: отбор опор линейный, а проверка габарита — по ломаной. Это ограничивает не сам sweep, а доступность и состав входных пар на повороте.

### Проверка GISLab-ELTE/railroad и выбор метода

Upstream проверен 2026-09-20: `railroad` заявлен для плотных MLS облаков, CLI принимает `cloud.laz`, а `StructureGaugeDetection` требует готовые rail seeds. Сборка ориентирована на Linux/Ubuntu 20.04 и требует PCL, OpenCV, Boost, LASlib/LASzip. Наши входы — одиночные `PointCloud2`/`xyzf`, без накопления и без проверенного alignment; для честного парного сравнения RailTrack не применим. Библиотека не устанавливалась.

Поэтому выбран один минимальный альтернативный метод выше: local-continuity path. PCL/Ceres не добавлялись: для этого ограничения не нужна новая зависимость, а их установка не устранила бы отсутствие проверенной геометрической разметки.

### Фиксированный development-набор и измерительная опора

| Случай | Evidence | Роль | Ограничение |
|---|---|---|---|
| `new_data` 0 | 159162 finite/non-zero return | прямая | только source-frame hypothesis `hesai_lidar <- hesai_lidar` |
| 5500 | 189666 | поворот | не мировая траектория |
| 1150 | 190316 | короткая/дальняя опора | не «дальность детекции» |
| 1054, 10000 | 189984 / 189078 | потеря **baseline** оси; 16/15 станций парных пиков | не доказанная физическая потеря рельсов: причина может быть кривой, стрелкой или инфраструктурой |
| `doubleT_obstacle` 168 | ручные source-return anchors рельсов | доступная поперечная/вертикальная проверка | это не абсолютная калибровка |
| 55 / 160 | пользовательские source returns OBS-002/OBS-003, полное облако с инфраструктурой | реальные низкие/одиночные точки | обе точки вне поддержанного сегмента, поэтому `UNKNOWN` |
| synthetic low singleton | одна добавленная только в RAM точка внутри опоры | защита от удаления малого низкого возврата | синтетика, не полевой случай |

Опоры 168 были ранее выбраны в существующем player и проверены как точные source returns (`1e-6`); поэтому это измерение в source XYZ, не CloudCompare и не внешняя калибровка. На ближней опоре `s≈5.553` оба метода имеют |Δx|=0.0769 и |Δz|=0.0714 м* к ближайшей станции `s=6`; дальняя отметка `s≈48.709` вне их опоры (конец `s=30`) и в ошибку не включена. Достаточной разметки для precision/recall/FP нет.

### Парный результат

Одинаковые source buffers, AutoRails config, reference profile, margins и реализация membership; 5 прогонов на случай. `UNKNOWN` — доля всех returns вне поддержанной оси, не «свободный путь». Число core returns — наблюдаемые геометрические пересечения, не число объектов и не FP.

| Кадр | baseline: длина / UNKNOWN / core | кандидат: длина / UNKNOWN / core | Результат |
|---|---:|---:|---|
| new 0 | 24.11 м / 0.500 / 899 | 28.44 м / 0.498 / 908 | длина больше, но опор для качества нет |
| new 5500 | 20.98 / 0.361 / 336 | 20.98 / 0.361 / 336 | идентично |
| new 1150 | 17.76 / 0.461 / 396 | 21.87 / 0.449 / 417 | неподтверждённое расширение |
| new 1054 | 0 / 1.000 / 0 | 30.00 / 0.452 / 514 | кандидат снимает `NO_STRAIGHT_CONSISTENT_PAIR`, но ось не размечена |
| new 10000 | 0 / 1.000 / 0 | 27.77 / 0.444 / 451 | то же ограничение |
| doubleT 168 | 26.19 / 0.574 / 916 | 26.19 / 0.574 / 916 | идентично, включая ручную опору |
| doubleT 55/160 | идентично | идентично | OBS-002 на 56.34 м после опоры 44 м; OBS-003 на 3.42 м до опоры 4 м — обе `UNKNOWN`, не пропущены и не подавлены |
| synthetic singleton | 917 core, synthetic point `CORE` | 917 core, synthetic point `CORE` | один низкий return не подавляется кластеризацией |

Каждая реальная или synthetic точка, попавшая в `CORE`, оставлена `OBSERVED_CORE_INTRUSION_CANDIDATE` без class/static/map suppression. В raw кадрах есть также `OUTSIDE_REFERENCE` returns; инфраструктурные точки без верифицированной разметки не были объявлены безопасными либо ложными тревогами.

Время (Windows, Node `v24.19.0`, Intel Core Ultra 7 265K; 5 повторов): для `new_data` baseline median 28.7–196.9 мс, кандидат 155.2–201.6 мс; для трёх real `doubleT` кадров baseline 293.1–312.1 мс, кандидат 294.5–313.4 мс. Граница замера — монотонное время pair extraction + axis + envelope membership; исключены I/O, PointCloud2 decode, ROS2, publish, очередь и viewer. Это не latency runtime и не real-time claim.

### Воспроизводимость

Команды:

```powershell
docker run --rm -v "${PWD}:/workspace" -w /workspace lidar-mosmetro3d:stage_3_baseline python3 scripts/experiment_new_data_baseline.py --archive dataset/for_hackathon/new_data --output artefacts/stage_5/raw_new_data --indices 0 1054 5500 10000 1150 --export-xyz
node --test tests/test_stage_5_rail_axis_experiment.cjs tests/test_live_envelope.cjs
node scripts/stage_5_rail_axis_experiment.cjs artefacts/stage_5/rail_axis_open_method_measured 5
```

Все три завершились успешно. Сырые фиксированные кадры и hashes: `artefacts/stage_5/raw_new_data/`; результат, configs, hardware, samples timing и membership: `artefacts/stage_5/rail_axis_open_method_measured_final/comparison.json`.

Дополнительно запускался `node --test tests/test_auto_rails.cjs`: вычислительные 5 тестов прошли, но весь запуск имеет прежний UI lifecycle failure (`auto-status` пуст вместо текста `Автоось`); данный эксперимент его не менял. Поэтому общий suite не объявляется зелёным.

### Safety-review (последовательный проход текущего агента, не независимый)

Вердикт: **не внедрять runtime-кандидат**.

- Профиль/margin, `hesai_lidar <- hesai_lidar`, timestamp contracts, deskew и карта не менялись; frames не накапливались.
- Кандидат сохраняет все core returns, включая singleton; не использует class, static/repeated/map evidence для отмены пересечения.
- Однако он превращает 1054 и 10000 из `UNKNOWN` в поддержанную ось без rail ground truth. Ошибка ломаной может создать ложное геометрическое пересечение или скрыть настоящее. Рост длины сам по себе не улучшение.
- Отсутствие опоры, точки до/после опоры и неразмеченные реальные люди остаются `UNKNOWN`; `CLEAR` не выводится.

### Validation review (последовательный проход текущего агента, не независимый)

Вердикт: **L1 только для изолированного offline сравнения; L0 для изменённого runtime, потому что его нет.**

Доказаны воспроизводимость input/hash, отсутствие изменения source buffers, идентичные profile/margins/checker, детерминированность пяти повторов, сохранение synthetic low singleton и bounded проверки JS envelope. Не доказаны абсолютная калибровка, поперечная/вертикальная ошибка на повороте, верность новых 1054/10000 осей, реальные TP/FP/FN, safety clearance, Humble runtime или real-time.

### Решение, риск и следующий тест

**Решение: оставить baseline; кандидат — только на доработку, не внедрять.** Его полезный диагностический сигнал — два baseline отказа при наличии локальных пар. Но без ручной проверки последовательных пар на 1054/10000 это может быть именно ошибочная длинная ось.

Следующий минимальный эксперимент: в существующем player или CloudCompare зафиксировать не менее трёх пар source-return rail-head anchors вдоль каждого из 1054 и 10000, включая начало/середину/конец candidate path; измерить ошибки к ним и вручную пометить несколько core/outside returns инфраструктуры. Затем повторить этот же manifest; внедрение рассматривать только если candidate не ухудшает проверенные ошибки и не переводит неподдержанные интервалы в наблюдаемую геометрию. Нужны отдельно валидные `base_link <- hesai_lidar`, профиль и margin для любого safety claim.

### Дополнительная проверка сечений 2026-09-20

После первичного отчёта повторно проверены спорные `new_data` 1054 и 10000. Для каждого взяты первая, средняя и последняя парные станции candidate path (шесть пар, 12 точек), построены raw `X/Z`-сечения шириной ±0.6 м по неизменённому source XYZ. Все 12 координат совпали с исходными возвратами ровно по выбранному допуску (для каждой стороны `exact_source_return_matches: 1`). Артефакты: `artefacts/stage_5/rail_section_visual_review/` и машиночитаемый `rail_section_review.json`.

Визуальная проверка показывает, что точки существуют в локальной геометрии, но не даёт независимого от кандидата однозначного назначения «головка рельса»: на дальних/разреженных сечениях им сопутствуют конкурирующие контуры лотка и инфраструктуры. Следовательно, исключена только ошибка «кандидат опирается на несуществующие точки»; не исключены неверный выбор пар и ошибка оси. Это candidate-assisted visual review, не абсолютная калибровка и не достаточное основание уменьшать `UNKNOWN`.

Команды дополнительной проверки:

```powershell
node scripts/stage_5_rail_axis_experiment.cjs artefacts/stage_5/rail_axis_open_method_review 1
docker run --rm -v "${PWD}:/workspace" -w /workspace lidar-mosmetro3d:stage_3_baseline python3 scripts/render_stage_5_rail_sections.py --comparison artefacts/stage_5/rail_axis_open_method_review/comparison.json --raw-dir artefacts/stage_5/raw_new_data --output artefacts/stage_5/rail_section_visual_review
node --test tests/test_stage_5_rail_axis_experiment.cjs tests/test_live_envelope.cjs
```

Все завершились успешно: последний узкий набор — 10/10. Локальная проверка не добавляет сама по себе safety claim или права автоматически переключать runtime; runtime остаётся L0. Сравнительное решение по явно заданному пользователем критерию уточнено ниже.

### Статистическое решение по парному критерию 2026-09-20

Критерий принятия: кандидат лучше/хуже baseline на одних и тех же реальных кадрах, без требования идеальной оси. В `artefacts/stage_5/rail_axis_open_method_measured_final/statistical_summary.json` сохранён воспроизводимый расчёт по восьми реальным одиночным кадрам (synthetic singleton исключён).

| Метрика | Baseline | Кандидат | Изменение |
|---|---:|---:|---:|
| Суммарная поддержанная длина | 160.39 м | 226.60 м | **+66.21 м, +41.28%** |
| Кадры по длине | — | 4 лучше / 0 хуже / 4 равны | без наблюдаемой регрессии |
| Returns `UNKNOWN` | 1 199 323 (61.24%) | 984 293 (50.26%) | **−215 030; −10.98 п.п.** |
| Core returns на кадрах с baseline-осью | не уменьшаются | +9, +21 или равны | нет class/static/map suppression |
| Median времени, 6 кадров где baseline уже имел ось | — | — | медиана **+0.29 мс**, среднее −0.53 мс |

Точный односторонний sign-test по четырём нетривиальным frame-level улучшениям длины (ties исключены) даёт `p=0.0625`. Это сильное направленное свидетельство в малом development-наборе, но не формальное подтверждение на заранее выбранном `alpha=0.05`. Возвраты внутри кадра коррелированы, поэтому нельзя ошибочно подменять восемь независимых наблюдений 1 958 324 точками.

На единственной доступной проверенной rail-anchor опоре 168 методы идентичны (|Δx| 0.0769 м, |Δz| 0.0714 м); на реальных low/person annotations оба оставляют `UNKNOWN`, synthetic singleton оба оставляют `CORE`. Precision/recall и повышение абсолютной точности оси не заявляются: для них нет достаточной независимой разметки.

**Решение по заданному сравнительному критерию: кандидат лучше baseline на измеренной coverage-статистике и не имеет наблюдаемой регрессии; принять его как следующий development/integration candidate.** Это не меняет runtime автоматически и не является safety/production acceptance: для переключения default нужны независимые anchors либо расширенный фиксированный набор, который снизит неопределённость sign-test и проверит геометрию на повороте.

Воспроизводимая команда статистики:

```powershell
node scripts/stage_5_compare_summary.cjs artefacts/stage_5/rail_axis_open_method_measured_final/comparison.json artefacts/stage_5/rail_axis_open_method_measured_final/statistical_summary.json
```

Последовательные проходы: safety-review подтверждает, что принятие не добавляет подавление реальных core returns и не объявляет `UNKNOWN` свободным; validation-review фиксирует L1 только для offline сравнения, отсутствие runtime change и ограничение `p=0.0625`/отсутствие axis ground truth.
