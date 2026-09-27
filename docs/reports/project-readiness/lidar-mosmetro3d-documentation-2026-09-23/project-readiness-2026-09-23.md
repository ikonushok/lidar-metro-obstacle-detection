# Документация, план и соответствие ТЗ — 2026-09-23

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Датированный аудит до редакции D0–D3; findings и рекомендации описывают тот срез. Текущие исправления документации указаны в отчёте D0–D3; runtime findings этим не закрыты.
> [Актуальный запуск](../../../../README.md) · [Текущий план](../../../README_work_plan.md) · [Результат D0–D3](../../../stages/stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Уточнение после ревизии: пользователь подтвердил положительный интервал 13–64, выполнение regression tangent и активный запуск CPU player с tangent/fmin=2/default model_v1. D04 теперь является вопросом актуализации исторического event registry, а не выяснения или исправления labels. D02 описывает отличие этого direct C++ запуска от отдельного ROS2 узла, а не ошибку плеера. Повтор tangent regression без нового изменения не требуется.

Проект: lidar_MosMetro3D. Режим: docs-vs-code. Тип: project-readiness. Цель — ревизия текущего состояния, расширений плана и remaining work. Стадия: исследовательский прототип; `HOLD` для общей готовности сдачи. L1 относится только к новым узким тестам, L0 — к сопоставлению документации. Это не повторение прежнего аудита.

## Что изменилось относительно общего плана

Текущий `docs/README_work_plan.md` уже знает о C++ CPU, development_candidate и tangent/arc_limited. Поэтому эти возможности нельзя целиком назвать «не учтёнными». Но его статус, перечень задач и критерии шага 3 отстали от последующих изменений. Код теперь содержит шумовой split, frozen tree, direct stream, arc_clamped и synthetic generator. Последовательность «каждый CORE → один JSON ROS node → пассивный viewer» больше не описывает все используемые режимы.

| Этап / работа | Что есть по code/config evidence | Что осталось по плану |
|---|---|---|
| 1. Humble/Docker, проверка входа | Dockerfile Jammy/Humble, input checker, extraction/replay scripts, local input tests | Свежая сборка release-кандидата, unit/integration lifecycle, новый путь/произвольный bag. Старые входные replay не подтверждают актуальную версию целиком. |
| 2. Данные, review и геометрия | Плееры, 7-source catalog, ручные anchors, assumed profile, event registry | Единый реестр источников и ролей train/dev/calibration/test; разметка событий; подтверждение геометрических предположений или явные ограничения demo. |
| 3. Envelope baseline | Python baseline и C++ axis/envelope/nearest/diagnostics реализованы | Завершение геометрического кода не равно доказанному качеству. Критерий «любой CORE даёт сигнал» конфликтует с текущими фильтрами. |
| 4. Визуализация и минимальная демонстрация | Lazy CPU viewer, raw/result identity; saved catalog; видео-preview файлы | Выбрать проверенные прямой/поворот/малый объект/loss-of-support случаи; финальный короткий ролик с актуальным runtime и README replay. |
| 5. Оценка и исправления | Полные frame-level summaries на 7 записях, tree model, noise filtering, axis/continuation experiments | Независимые positive examples, matching/event metrics, оценка FN/UNKNOWN по range/size; правильный timing и сравнение режимов на одной версии. |
| 6–8. Сквозная сдача | Исходники, build/replay инструменты, reusable core | Один release path; clean Linux launch; длительный ROS replay; очередь/drops/ресурсы; согласованные документация/параметры/видео; контрольный bag организаторов. |

## Расширения, недостаточно отражённые в общем плане

«Вне плана» здесь означает отсутствие в актуальной общей сводке/очереди работ. Отдельные документы фиксируют пользовательские решения; отсутствие строки в общем плане не доказывает отсутствие разрешения.

| Расширение | Evidence | Классификация и дальнейшая судьба |
|---|---|---|
| Legacy noise filter и viewer temporal policy | C++ core; `web/stage_4_cpu_player.js`; stage_5_filter_restore | Изменение смысла alarm относительно raw CORE. Внести отдельный режим/acceptance; проверить малые и близкие объекты. |
| Decision Tree v1 + offline evaluation + CPU player default | train/evaluate scripts, frozen tree, launcher `NoiseFilterMode=model_v1` | Уже реализованное ML-расширение. Оно не обязано входить в первый baseline, но теперь реально влияет на default viewer. |
| Direct C++ transport | `DirectDetailedCpuRuntime`, serve selection | Ускорение development-плеера; требует отдельного доказательства parity с ROS node. |
| arc_clamped, smooth-window/radius/turn guards | C++ extension API, node/stream args, launcher | Эксперимент после tangent/arc_limited. Нельзя считать гарантированно безопаснее только из-за ограничения угла: возможен уход от реального объекта. |
| Synthetic box/cylinder ROS generator | `src/synthetic_obstacle_generator.py`, config, tests | Уже реализованный инструмент проверки низких/малых объектов. Следующий шаг — replay и визуальная проверка, затем контролируемые regression cases. |
| Полный seven-source catalog и статистика | SOURCES; export/render/merge; семь summaries | Существенно больше, чем заявленные в общем плане 101 development-кадр. Но это не полный ROS streaming benchmark и не независимый test. |
| ICP/шпалы/дальность исходных возвратов | estimate/probe/audit scripts и JSON | Полезная диагностика данных. Не включать в TTC/deskew до подтверждения движения/часов и проверки ошибки. |
| YOLO grayscale в root README | Только пример текста; соответствующего config/dependency/runtime нет | Отдельная 2D-идея; не реализованная часть LiDAR MVP. Вынести в research notes при редактировании документации. |

## Конкретные несоответствия активных документов

| ID / важность | Документ и утверждение | Что фактически есть | Как актуализировать |
|---|---|---|---|
| D01 / P1 | `README_work_plan.md`, шаг 3: каждый CORE return становится candidate независимо от группы | Node использует reportable count; legacy и model подавляют часть raw CORE; тест C++ явно ожидает singleton в noise | Развести `raw_core_return_present`, reportable signal и system health; не называть старый singleton acceptance проверкой нынешнего alarm. |
| D02 / P1 | `README.md`, запуск CPU player: matching JSON от C++ CPU node; план также строит путь вокруг ROS node | Default development branch — direct stream + model; ROS branch — legacy | Добавить таблицу runtime, параметры, source frame, значения margin/filter, distance basis и текущий путь сдачи. |
| D03 / P1 | `README_noise_classifier.md`: production-like без wireframe/debug и сравнение полного времени фильтров | Stream CLI выполняет legacy + model + wireframes перед lean if; время фильтра считается повторно | Отозвать перенос старого timing на текущую сборку; исправить code/timing отдельной задачей и только затем обновить числа. |
| D04 / P1 | Event registry: два пользовательски подтверждённых человека/помехи; model docs/train: positive только 13–64, остальные компоненты negative | JSON anchors содержит OBS-002/55 и OBS-003/160; trainer выбирает largest reportable лишь в positive interval | Объяснить, что считать целевым событием именно внутри габарита, судьбу OBS-003 и статус остальных кадров. Не объявлять разметку ошибочной автоматически: разные scope могут быть обоснованы, но сейчас они не сведены. |
| D05 / P2 | `README_methodology.md:7`: «детектор пока не реализован» | Python и C++ detectors реализованы | Обновить статус; отделить исполняемый C++ метод от концепций background/PCA/tracking/risk. |
| D06 / P2 | `README.md`: `.python-version=3.12.3`, прежние NumPy/SciPy/PyYAML фиксации, среда не мигрирована | Файл=3.10, requirements=numpy/matplotlib, Docker Humble; Windows .venv=3.12.10 | Описать две среды. ТЗ не требует пересоздать локальную Windows .venv. |
| D07 / P2 | `README.md`: src — «будущие ROS2-пакеты», старые пути в дереве; ближайшее действие — ещё реализовать CurveRailAxis | Пакет уже есть, CurveRailAxis реализован, документы переименованы README_* | Обновить дерево, статус, ближайший шаг. |
| D08 / P2 | Root README: `docker stop lidar-cpu-catalog-8099-development_candidate` | Launcher добавляет fmin/extension/arc/radius/turn/fit/noise в имя | Использовать имя, напечатанное launcher, либо документировать точное имя текущего запуска. |
| D09 / P2 | `README_dataset_audit.md`: new_data geometry OFF; только 3 sampled clouds, full pass не выполнен | Catalog подключает new_data; есть все 11 271 saved evaluation results в summary; исходная малая выборка остаётся валидной историей | Сохранить 12+3-cloud аудит как исходный срез; добавить отдельный датированный слой текущего покрытия, без переноса всех старых schema-выводов на полный набор. |
| D10 / P2 | `README_train_clearance.md`: «текущая» стратегия straight/margin 0,20 + warning bottom 1,30; extrinsics численно пусты | Это Python YAML scope; C++ default expanded margin=0,5 по сторонам, axis curve; YAML identity уже заполнен как ASSUMED | Подписать применимость к Python baseline; добавить C++ scope и заменить «пусты» на «предположены, не откалиброваны». Числа этой ревизией не менять. |
| D11 / P2 | `README_noise_classifier.md` одновременно говорит «модель подключена» и «до подключения остаётся offline», диаграмма ведёт current player через старый фильтр | Header/launcher подтверждают default model_v1 | Переписать пункты 6–7, Mermaid и pre-integration рекомендации как историю/remaining validation. |
| D12 / P2 | AGENTS.md и все 5 agents ссылаются на methodology/work_plan/dataset_audit без README_ | Этих путей нет | Исправить маршрутизацию на существующие имена; это технические ссылки, не изменение инвариантов. |
| D13 / P2 | `stage_5_accept_fmin2_default_and_frame23_diagnostic.md`: не осталось defaults 3,0 | Новый direct runtime снова имеет default 3,0; launcher передаёт 2,0 | Исторический результат не обобщать на весь текущий source tree. Унифицировать defaults отдельным минимальным изменением с проверкой callers. |
| D14 / P2 | `stage_5_synthetic_obstacle_generation_run.md`: Python312 отсутствует | В этой сессии .venv Python 3.12.10 успешно запускается; первоначальный sandbox запуск действительно отказал | Отметить историческую/сессионную границу; ошибку доступа не считать доказательством отсутствия Python у пользователя. |
| D15 / P2 | `stage_5_axis_sequence_validation_review.md`: «проверка выполняется» | Файл не содержит итогового verdict | Не считать review завершённым; закрыть итогом либо пометить незавершённой исторической задачей. |
| D16 / P2 | Текущий план цитирует p95 84,61/291,74; основной доступный `cpu_catalog_metrics.json` содержит 84,981/280,879 и не сохраняет rail_selection_method | Нет устойчивой привязки цифр к run/config; мог существовать иной исторический run | Прикрепить конкретный неизменяемый manifest/hash к каждому числу, не заменять исторические значения молча. |

`README_LiDAR_Specifications.md` содержит характеристики производителя, а не свойства алгоритма. Кодом нельзя подтвердить паспорт, firmware или реальный монтаж; внешние характеристики в этой ревизии не перепроверялись. Документ корректно не приравнивает sensor range к detection range. `README_dataset_describtion.md` уже различает source ranges, движение и метраж; его sample-based цифры нельзя распространять на все кадры.

## Старые отчёты и полнота Markdown

Проверены 124 исходных MD: 14 активных/справочных/instruction files и 110 stage/task/report files. [Индивидуальный реестр](markdown-inventory.md) отмечает scope каждого, ключевые риски и code evidence. Он не присваивает всем файлам фиктивный PASS: часть содержит историю, plans, externally sourced facts либо невоспроизведённые старые результаты.

Исторические «ещё не реализовано», старые defaults или FAIL могут быть правдивы на дату отчёта. Правильное исправление — дата/revision/scope и ссылка на преемника, а не переписывание истории под текущий код. Например, старые JS lifecycle FAIL сейчас не повторились (58/58 PASS); старый stage-3 gate без detector больше не описывает нынешний checkout.

9 файловых Markdown links в 4 stage-3 run reports ведут на отсутствующие artefacts. `stage_1_disk_cleanup.md` описывает ранее согласованное удаление ряда таких outputs. Это не доказательство ложности исторического запуска; но пересмотреть evidence сейчас по ссылке нельзя. Нужна пометка «артефакт очищен, воспроизвести командой …». Внешние URL, все anchors и точность каждой давней цифры не проверялись.

## Проверка требований ТЗ

Источник: `docs/hackathon_documentations/5. ДепТранспорта.pdf`, извлечён текст всего документа. Таблица не повышает роль наших внутренних критериев до требований организатора.

| ТЗ | Evidence / текущая граница |
|---|---|
| §2: потенциальное препятствие и ближайшее расстояние | Candidate algorithms существуют. Реальное качество, точность расстояния и покрытие сценариев требуют разметки. `UNKNOWN` не «препятствия нет». |
| §3: Ubuntu 22.04, Humble, Docker, автоматические зависимости | Соответствующий Dockerfile/package есть. Fresh build текущей working tree не выполнен; local pip manifest неполон. Конкретного требования Python 3.10 в PDF нет. |
| §3.3–4: container → ROS2 bag → обработка → результат и визуализация | Отдельные части есть, но текущая default модель viewer не встроена в ROS node. Требуется единая сквозная демонстрация. |
| §5: README build/run/bag/config, architecture, algorithm, experiments, short video | Материалов много; README устарел, конфигурации разных веток смешаны. Видео-preview существуют, содержание и актуальность финального видео не подтверждены. |
| §7: промежуточная/финальная сдача | Прототип и исходники есть; финальный immutable release, воспроизводимость на стенде и контрольный bag не подтверждены. |
| §8: обнаружение, false alarms/misses, range, latency/FPS/resources, unseen data | Семь development summaries — прогресс. Один обучающий positive, условные negatives и неоднозначный current timing не закрывают эти критерии. 100/200/300 м — ориентиры ТЗ, не обязательные фиксированные пороги. |

## Evidence, проверки и последующая работа

Команды/результаты: git status/diff, rg inventory/import/contract searches, Get-Content и bounded Markdown claim extracts; pypdf с UTF-8; Node 58 PASS; Python 71 OK + 4 ERROR; JSON sums; локальные file-link checks. См. [index](index.md) и [code-only report](code-only-project-readiness-2026-09-23.md). Mandatory bug discovery выполнен, подтверждённые code contradictions и ещё не воспроизведённые кандидаты разделены в [bug audit](bug-audit-2026-09-23.md).

Уровень: L0 для docs-vs-code, L1 только для названных tests. Не проверены физическая калибровка, current C++ build/replay, стенд, independent labels, внешний паспорт датчика и точность исторических runtime-утверждений. Риск — считать насыщенную экспериментальную документацию доказательством готового продукта. [Новый порядок работ](work-plan-revision.md) сначала закрывает signal/runtime/timing/labels; новые модели и дальность исследуются после измерения этих основ.
