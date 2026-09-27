# Аудит расстояний по источникам — 2026-09-22

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

## Задача

- Goal: дополнить `docs/README_dataset_describtion.md` измеряемыми расстояниями по каждому исходному источнику, не подменяя расстояние до возврата пройденным метражом.
- Наблюдаемая проблема: документ верно сообщает, что пройденный метраж неизвестен, но не даёт сопоставимой измеренной дальности LiDAR-возвратов для источников.
- Non-goals: восстанавливать траекторию/одометрию, менять геометрию, оси, единицы, TF, детектор либо использовать результат как дальность обнаружения препятствий.
- Source of truth: `docs/README_dataset_describtion.md`, `docs/README_dataset_audit.md`, исходные ROS 2 bag в `dataset/for_hackathon/` и schema-aware `src/cloud_input.py`.
- Этап: 5 — измерение и distance-aware evidence.
- Целевое окружение: Ubuntu 22.04 + ROS 2 Humble + Docker; фактическая проверка: существующий контейнер проекта, если он доступен.
- Входные данные и единицы: ненулевые конечные XYZ; измерение — `sqrt(x²+y²+z²)` от начала координат source frame. Метры — только при существующем проектном допущении; внешняя калибровка единиц/экстринсиков отсутствует.
- Конкретный bag/объём: все шесть сцен `for_hackathon` и `new_data`; для каждой строки будет явно указан фактически прочитанный объём.
- Факты и границы: нет odometry, скорости, TF или проверенного межкадрового совмещения; путь поезда и дальность объектов из одной дальности возврата не выводятся.
- Рабочие frames/transforms: исходные `hesai_lidar` или `lidar_livox`; transform не применяется.
- Allowed files: этот отчёт, `docs/README_dataset_describtion.md`, узкий reader `scripts/audit_source_return_ranges.py`, новые JSON/CSV evidence в `artefacts/stage_5/`.
- Files to avoid: исходные bag, production-код, параметры геометрии, ROS2-схемы.
- Защищённые контракты: `UNKNOWN != CLEAR`; source frame не переименовывается; расстояние от LiDAR не называется пройденным путём/дальностью обнаружения.
- Основной агент: `agents/lidar_obstacle_pipeline.md`; safety-review не нужен — защищённая геометрия не меняется. Отдельный validation-проход нужен для формулировок evidence.
- Validation target: L1 для фактически прочитанных облаков и статистики; L0, если среда не позволяет десериализовать источники.
- Validation method: schema-aware CDR-десериализация, исключение неfinite и `(0,0,0)`, расчёт максимумов/квантилей расстояния; сверка counts с metadata.
- Acceptance criteria: таблица по каждому источнику содержит scope, число прочитанных облаков, измеренный максимум и недвусмысленное ограничение интерпретации.
- Stop conditions: нужна новая зависимость, изменение входного контракта или вычисление пути без независимой одометрии/валидации регистрации.

## Отчёт о завершении

- Что изменено: добавлена воспроизводимая schema-aware утилита `scripts/audit_source_return_ranges.py`, два JSON-артефакта и таблица выборочной дальности LiDAR-возвратов в `docs/README_dataset_describtion.md`.
- Evidence inspected: `README_dataset_describtion.md`, `README_dataset_audit.md`, metadata и SQLite-сообщения семи источников. Для `doubleT_obstacle`, `roundT_squareT_pressureGate_squareT` и `squareT_platform_squareT_switch` подтверждено известное расхождение вложенной суммы `files[].message_count` с верхним count; reader использует верхний count только для single-file source и сверяет фактический SQLite count.
- Commands run:
  - `docker run ... stage_2-player python3 scripts/audit_source_return_ranges.py --archive dataset/for_hackathon/new_data --output artefacts/stage_5/source_return_ranges_new_data_2026-09-22.json` — PASS, 3/3 контрольных кадра `new_data`.
  - `docker run ... stage_2-player python3 scripts/audit_source_return_ranges.py --archive dataset/for_hackathon/for_hackathon --output artefacts/stage_5/source_return_ranges_for_hackathon_2026-09-22.json` — PASS, по 3/3 кадра шести сцен.
  - Первый объединённый запуск остановился на нормализации имён `./new_data/...` в TAR; reader исправлен, после чего оба раздельных прогона завершились успешно.
- Результаты: все 21 выбранных PointCloud2 штатно десериализованы. Наблюдаемый максимум среди выбранных кадров — 209,108 м в `doubleT_obstacle`; для `new_data` — 208,216 м. Полная таблица и границы интерпретации добавлены в README.
- Validation level achieved: L1 для измерений 21 конкретного облака и статически согласованной документации. Verdict: PASS_WITH_RISKS.
- Что не проверено: остальные кадры каждого источника, внешний метрический контракт, extrinsics, оси, объектная разметка, дальность первого/устойчивого детектирования и пройденный метраж.
- Известные FP/FN или safety-риски: большой дальний возврат может быть стеной/инфраструктурой и не свидетельствует о наблюдаемости низкого препятствия. `UNKNOWN` не становится `CLEAR`; числа нельзя применять как FP/км.
- Следующий минимальный тест: при появлении одометрии или валидированной trajectory измерить путь отдельно; для object-level distance — разметить интервал видимости объекта и измерить первое/устойчивое обнаружение на известных range slices.
- Residual risk: три кадра (начало/середина/конец) не характеризуют весь источник; `m_ASSUMED` нельзя выдавать за калиброванный измерительный результат.
