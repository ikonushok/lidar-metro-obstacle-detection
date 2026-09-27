# Маршрутизатор контекста

Цель: выбрать минимальный набор файлов, одного основного агента, не более одного reviewer и достижимый уровень валидации.

## Inputs / Входы

- запрос пользователя;
- `AGENTS.md`;
- релевантные требования `docs/hackathon_documentations/5. ДепТранспорта.pdf`, этап/очередь `docs/DEVELOPMENT_HISTORY_AND_STATUS.md` и факты `docs/DATASETS_AND_ASSUMPTIONS.md`;
- релевантные разделы `docs/METHODOLOGY.md`;
- для сдачи: `docs/SUBMISSION_CHECKLIST.md` как упаковочный чеклист и `docs/reports/submission/` как датированные evidence-отчёты;
- только связанные с задачей код, конфигурации, тесты и вывод команд.

## Task Modes / Сначала классифицировать задачу

- `inspect` — понять данные, код или текущее поведение без изменений;
- `plan` — спроектировать изменение и критерии проверки;
- `patch` — изменить реализацию, конфигурацию или интерфейс;
- `calibration` — подобрать параметры только на calibration-наборе;
- `validation` — проверить конкретное утверждение;
- `release/demo` — проверить воспроизводимость демонстрации и ограничения.

## Routing / Маршрутизация

Select one primary agent and at most one triggered reviewer.

При пересечении триггеров геометрии и метрик: реализация → safety-review → отдельная validation доказательств. Ограничение «один reviewer» относится к этапу, а не запрещает последовательные проверки. Роли могут исполняться отдельными проходами текущего агента; это не независимое внешнее review.

| Триггер | Primary context / первый контекст | Основной агент | Reviewer | Проверка |
|---|---|---|---|---|
| Обычная локальная правка | `AGENTS.md`, файл задачи, соседний тест | текущий агент по правилам `AGENTS.md` | нет | узкий тест |
| PointCloud2, ROI, filtering, clustering, tracking, ROS2 pipeline | релевантные части `docs/METHODOLOGY.md`, код и конфиг стадии | `agents/lidar_obstacle_pipeline.md` | нет по умолчанию | тест стадии + replay/smoke при наличии данных |
| TF, часы, deskew, alignment, envelope, background, risk, temporal policy, фильтры или геометрические/distance-aware пороги | методология + аудит + изменённые контракты и тесты | `agents/lidar_obstacle_pipeline.md` | `agents/safety_geometry_reviewer.md` | границы/низкое препятствие/сбой нужного входа; затем отдельно validation метрик |
| Evaluator, matching, split или оценка метрик | раздел 17 методологии, аудит, split manifest, evaluator, config | `agents/lidar_obstacle_pipeline.md` | `agents/validation_reviewer.md` | split-by-run и отчёт по срезам; изменения детектора сначала по строке safety |
| Docker, зависимости, окружение Humble | ТЗ §3, этап 1 плана, существующие Dockerfile/requirements/package manifests | `agents/lidar_obstacle_pipeline.md` | `agents/validation_reviewer.md` | сборка без ручных зависимостей, чтение обычного и obstacle bag; проверить формат/QoS |
| Аудит датасета | docs/DATASETS_AND_ASSUMPTIONS.md, metadata, schema/topics, малые образцы | `agents/lidar_obstacle_pipeline.md` | нет для чтения | объём выборки, структура и факты отдельно от гипотез; изменение входного контракта направить в safety |
| Промежуточная/финальная сдача | ТЗ §4–8, `docs/DEVELOPMENT_HISTORY_AND_STATUS.md`, `docs/SUBMISSION_CHECKLIST.md`, `docs/reports/submission/`, README/SOLUTION, артефакты и вывод запусков | `agents/lidar_obstacle_pipeline.md` | `agents/validation_reviewer.md` | checklist сдачи, чистая сборка/run/replay, новый путь bag, видео и эксперименты |
| Утверждение «тесты прошли», «real-time», «готово» | изменённые файлы и полный вывод команд | `agents/validation_reviewer.md` | нет | L0–L5 по доказательствам |
| Многофайловая задача | запрос и допустимый scope | `agents/task_spec_short.md`, затем профильный агент | только по триггеру | из task spec |

## Контекст по подсистемам

Загружать только существующие пути и ближайшие зависимости:

- вход/TF: ROS2 subscribers, transform helpers, timestamps, launch и bag metadata;
- окружение: ТЗ §3, Dockerfile/build context, зависимости, версия интерпретатора и ROS, вывод сборки и запуска;
- envelope: геометрия профиля, path/trajectory input, margins, visualization и тестовые случаи;
- background: map builder, reference cloud/voxel occupancy, localization quality и update policy;
- clustering/features: range bands, voxel/KD-tree/DBSCAN, boxes, PCA и synthetic clusters;
- temporal/risk: association, track state, confirmation, TTC, score и diagnostics;
- evaluation: event annotations, split manifest, matching, ablations и latency profiling.
- сдача: ТЗ §4–8, этап плана, чеклист упаковки, README/SOLUTION, код, архитектура/алгоритм, experiments/evidence reports и видео; проверять наличие и воспроизводимость, не только описание.

Не читать весь датасет, архивы, bag-файлы или весь репозиторий без необходимости. Сначала изучить метаданные, небольшой репрезентативный фрагмент и интерфейсы.

## Output / Выход маршрутизатора

Перед работой зафиксировать:

- режим задачи;
- цель и non-goals;
- файлы для чтения и файлы, которых не касается изменение;
- основной агент;
- нужен ли safety/validation reviewer;
- защищённые контракты;
- target validation level / целевой уровень валидации и конкретные команды/сценарии;
- stop conditions.
- путь отчёта: `artefacts/task_specs/` для выполнения этапа либо `docs/reports/<category>/` для прочего отчёта.
