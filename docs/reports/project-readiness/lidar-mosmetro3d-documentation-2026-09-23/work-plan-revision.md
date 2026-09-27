# Предлагаемая актуализация плана — 2026-09-23

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Датированный аудит до редакции D0–D3; findings и рекомендации описывают тот срез. Текущие исправления документации указаны в отчёте D0–D3; runtime findings этим не закрыты.
> [Актуальный запуск](../../../../README.md) · [Текущий план](../../../README_work_plan.md) · [Результат D0–D3](../../../stages/stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Уточнение пользователя после составления плана: используется `tangent` с `RailForwardMinM=2`, default `development_candidate/model_v1`; полный regression tangent выполнен. Положительный интервал 13–64 подтверждён как правильный. Повторять этот прогон и выяснять labels заново не требуется. Для строки 3 ниже остаются оформление принятого правила и split/matching; текущая разметка не меняется. Различие с ROS legacy относится к будущему пути сдачи, текущий CPU player уже применяет модель. Первая адресная правка — timing B01.

Цель: завершить уже созданный прототип до воспроизводимой демонстрации и измеримой оценки. Категория project-readiness; охватывает этапы 1–8. Это предложение очереди, **не изменение геометрических/сигнальных контрактов и не разрешение на настройку по test**. Основание — code trace и новые проверки из [индекса](index.md). Уровень L0 для планирования, L1 только для названных там tests.

## Что считать сделанным

- **Вход и базовая инфраструктура:** PointCloud2 reader, Humble Dockerfile, C++ ROS package, extraction/replay tools; текущую release-сборку ещё проверить.
- **Геометрический baseline:** Python и C++ ветки, AutoRails development_candidate, curve envelope, candidate/UNKNOWN, nearest source return, raw/reportable split.
- **Средства разработки:** CPU viewer семи источников, ручные anchors, полные offline catalog/preview инструменты, автоматические tests.
- **Эксперименты этапа 5:** noise tree v1, сравнение 13 759 кадров по условной разметке, tangent/arc_limited/arc_clamped, synthetic generator, motion diagnostics.

Не отмечать как завершённые: независимое качество, диапазон 100/200/300 м, калибровку, real-time, единый ROS/viewer inference, финальную сдачу и низкие препятствия после noise suppression.

## Очередь работ с критериями выхода

| Порядок | Задача / этап | Конкретный результат | Критерий завершения |
|---|---|---|---|
| 0 | Синхронизировать активную документацию / все этапы | Исправить D01–D16; добавить runtime table, current status, actual environment; заменить пути README_* в agent pack; исторические reports оставить датированными | Каждый current claim имеет code/config/evidence ссылку; singleton/raw/reportable/UNKNOWN не смешаны; ссылки проверены; новые численные promises не добавлены. |
| 1 | Зафиксировать release-кандидат и сигнальный контракт / 3–5 | Выбрать один effective config: rail selection, continuation, filter, distance basis; описать роли Python/ROS/direct/browser. Согласовать, что значит raw intrusion и filtered alarm | ROS node и viewer одного release показывают одинаковые решения на четырёх контрольных случаях. Если model остаётся только research — это явно видно в README и demo. Любое изменение protected decision/thresholds имеет отдельный test plan. |
| 2 | Исправить timing и test lifecycle / 4–6 | Непересекающиеся timers, отдельный active path, отдельные unit/integration команды | Один frame wall time согласован с измеренными стадиями; lean не выполняет выключенный comparator/wireframe; чистая проверка не зависит от случайно работающего localhost сервера. Затем длинный benchmark заново. |
| 3 | Согласовать ground truth и split / 2, 4–5 | Один event registry с OBS-002/OBS-003 и training interval 13–64, статус каждой записи; версия разметки и event matching | Каждое исключение/negative label объяснено; положительный объект не исчезает из оценки из-за unsupported geometry; independent positive test либо выделен, либо явно отсутствует. Соседние кадры не делятся между train/test. |
| 4 | Проверить малые/низкие препятствия и loss-of-support / 3–5 | На неизменной геометрии сравнить raw, legacy и tree; использовать готовый synthetic generator как development supplement | Таблица размеров/дальности, raw visibility, CORE/reportable/UNKNOWN и причины FN. Synthetic не выдаётся за реальный unseen positive. Отрицательное решение фильтра не трактуется как CLEAR. |
| 5 | Оценить реальное качество / 4–5 | Event TP/FP/FN, frame alarms отдельно, FP/мин, distance error, first/stable range, UNKNOWN coverage по прямым/кривым и range/size | Воспроизводимые before/after на одинаковых данных/config; неизвестная геометрия не исключена из positive recall без отдельного учёта. Все наборы, denominator и границы claims названы. |
| 6 | Сквозной ROS2 replay / 6–7 | Bag → выбранный detector → matching viewer, новый путь bag, malformed/no support сценарии, длинный поток | Ubuntu 22.04/Humble/Docker, зависимости при build; измерены delivery/queue/drops, p50/p95, CPU/RAM и оборудование; результаты не подменены offline direct benchmark. |
| 7 | Сдача / 7–8 | Linux build/run/replay инструкции, полный список параметров, current architecture, короткое видео четырёх контрольных сценариев, frozen commit/image/config | Запуск по README из чистого checkout; viewer показывает именно выбранный алгоритм; видео/цифры относятся к этой версии; контрольный bag тестируется только когда предоставлен. |

Шаги 0–3 могут готовиться одновременно организационно; зависимые code changes и acceptance выполняются последовательно. Новые субагенты для этого плана не требуются. В этой ревизии код/порог/split не менялись.

## Новые идеи, вытекающие из кода

1. **Сначала ускорить компоненты, затем менять модель.** В legacy и frozen tree есть полный перебор соседей по raw CORE; stream вычисляет компоненты дважды. Гипотеза: reuse одного component graph и пространственный hash дадут больше эффекта, чем смена компактного дерева. Проверка — один frozen набор, полное равенство component memberships/decisions и p95. Это предложение, не измеренный выигрыш; новые библиотеки не обязательны.
2. **Проверять continuation скрытой наблюдаемой опорой.** Отрезать часть известных rail pairs, предсказывать продолжение и сравнивать с оставленной опорой отдельно для прямых/поворотов. После этого смотреть target hits и UNKNOWN. Так можно выбирать tangent/arc по ошибке геометрии, а не по красоте картинки.
3. **Версионировать результат вместе с методом.** Сохранять code revision/dirty hash, effective config, model hash, source/frame window и точное определение таймеров. Сейчас общий JSON `cpu_catalog_metrics.json` легко переживает смену default и теряет применимость. Это минимальный способ перестать смешивать эксперименты.
4. **Разделить raw intrusion и filtered alarm в acceptance и интерфейсе.** Raw CORE уже сохраняется; использовать его для контроля пропусков фильтра и явного объяснения «видели точки, но alarm подавлен». Новые статусы или policy требуют отдельного согласования ROS/diagnostic contract; здесь предлагается сначала описать существующие поля.
5. **Короткая автоматическая проверка документации.** Проверять file links, canonical README_* paths и наличие revision у численных claims. Не запрещать исторические документы: отмечать superseded/cleaned evidence и выводить missing current links отдельно.

## Что пока отложить

- Новые Random Forest/LightGBM/нейросетевые эксперименты до появления независимых positive examples и исправного timing. Модель v1 уже показывает конкретный риск зависимости от размера объекта.
- Deskew, mapping, temporal accumulation, TTC — до валидных входных времён и движения и измеренной причины ошибки baseline.
- GPU default — до сравнения полного пути на целевом стенде; CPU остаётся обязательным воспроизводимым вариантом.
- Автоматическое увеличение envelope до 200 м и подбор порогов по всем имеющимся данным: это не заменяет наблюдаемую опору и отдельный test.

## Проверки, риск и следующий шаг

Evidence: actual sources/defaults, saved seven-source counts, current test logs и PDF требований; команды и результаты перечислены в index. Ревизия не запускала новый ROS replay, не обучала новую модель и не оценивала unseen data. Остаточный риск — выбрать удобную визуализацию вместо физически обоснованного метода. Самая маленькая следующая работа: актуализировать runtime/signal таблицу и проверить текущий timing B01; после этого зафиксировать набор из известной помехи, чистого окна, низкого объекта и отсутствующей опоры для сравнения одного release path.
