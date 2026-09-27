# Что именно выполняет команда запуска

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Датированный аудит до редакции D0–D3; findings и рекомендации описывают тот срез. Текущие исправления документации указаны в отчёте D0–D3; runtime findings этим не закрыты.
> [Актуальный запуск](../../../../README.md) · [Текущий план](../../../README_work_plan.md) · [Результат D0–D3](../../../stages/stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Дата: 2026-09-23. Проект: lidar_MosMetro3D; категория project-readiness; тип code-only-project-readiness. Режим: статическая трассировка исполнимого кода плюс узкие проверки. База `4d5bb30`; дополнительные изменения рабочего дерева перечислены в реестре. Markdown не использован как доказательство работы алгоритма.

**Пункт 2 запускает прямой C++-плеер с моделью, без ROS2 pub/sub в обработке запрошенного кадра.** ROS-библиотеки остаются зависимостью чтения bag и образа. Отдельный C++ ROS2 node реализован и также использует model_v1 по умолчанию.

## Карта действующего пути

| Ступень | Исходник | Что делает |
|---|---|---|
| PowerShell launcher | [run_stage_2_cpu_player.ps1](../../../../scripts/run_stage_2_cpu_player.ps1), параметры 1–28, выбор транспорта 37, проверки файлов 40–45 | Собирает CPU-образ и запускает каталог на localhost:8100; `development_candidate` выбирает direct_cpp |
| Образ | [Dockerfile](../../../../Dockerfile) | `ros:humble-ros-base-jammy`, apt-зависимости, colcon C++; default CMD сам по себе выводит help input-аудитора, поэтому нужна явная команда запуска |
| HTTP и источники | [serve_stage_2_cpu_catalog.py](../../../../scripts/serve_stage_2_cpu_catalog.py), 15–31, 60–82 | Семь источников из двух TAR; общий обработчик результата; evaluator-аннотации не передаются детектору |
| Получение XYZ | [archive_bag_frames.py](../../../../scripts/archive_bag_frames.py) | metadata → извлечение SQLite → CDR/PointCloud2 → конечные ненулевые XYZ; сохраняется соответствие индексов визуализации |
| Прямой адаптер | [cpu_catalog_runtime.py](../../../../scripts/cpu_catalog_runtime.py), 189–282 | Постоянный `curve_pipeline_stream_cli`, binary stdin: количество точек + float32 XYZ; одна строка JSON в stdout; source frame/timestamp добавляются к результату |
| Рельсы | [auto_rails_core.cpp](../../../../src/cpp/auto_rails_core.cpp) | `development_candidate`: локально согласованная цепочка наблюдаемых пар; исходный baseline сохранён отдельно |
| Габарит и модель | [curve_pipeline_stream_cli.cpp](../../../../src/cpp/curve_pipeline_stream_cli.cpp), 131–234; [curve_envelope_core.cpp](../../../../src/cpp/curve_envelope_core.cpp), 551 и далее | Тангенциальное продолжение, CORE, компоненты, frozen tree; raw CORE не теряется |
| Отображение | [stage_4_cpu_player.js](../../../../web/stage_4_cpu_player.js), `backendModelSplit`/`effectiveCoreSplit` | При model_v1 принимает готовые obstacle/noise индексы и расстояние backend; старые JS noise/temporal правила не определяют сигнал этого режима |
| Отдельный вход сдачи | [curve_envelope_node.cpp](../../../../src/lidar_mosmetro3d_cpp/src/curve_envelope_node.cpp), 28–39, 227–253 | PointCloud2 → общее ядро → model_v1 → `std_msgs/msg/String` JSON; плеер не нужен |

## Эффективная конфигурация пункта 2

| Параметр | Значение / смысл |
|---|---|
| transport / compute | direct_cpp / CPU |
| rail_selection_method | development_candidate |
| forward_min / max | 2 / 80 м; max — граница поиска/continuation, не доказанная дальность детекции |
| station / cell | 2 / 0,04 м |
| continuation | tangent: синтетическая последняя пара после наблюдаемой опоры, явно помеченная в JSON |
| core / expanded | Локальное сечение CORE x=[−1,4;1,4], z=[0;3,7]; expanded x=[−1,9;1,9], z=[−0,5;4,2]. Это константы данного C++ пути; старый YAML Python-baseline не управляет ими |
| noise_filter_mode | model_v1; связность 0,25 м, дерево принимает компонент при `extent_z_m > 0.3665030598640442` **и** `point_count > 104` |
| модель | [Версионированный JSON](../../../../models/noise_classifier_doubleT_obstacle_v1.json) соответствует frozen tree; runtime использует C++ реализацию дерева, не читает JSON весов при каждом кадре |
| расстояние | Ближайшая reportable точка от source origin; не расстояние от носа поезда и не тормозной путь |
| system/safety | `system_status=UNKNOWN`, `safety_decision_permitted=false`; отсутствие reportable не означает CLEAR |

Default `DirectDetailedCpuRuntime` в Python отдельно равен 3 м, но launcher явно передаёт 2 м. Это рассогласование defaults не изменяет рассматриваемую команду.

## Что не включено этой командой

- `arc_limited`, `arc_clamped`, observed-only, baseline selection и legacy filter — отдельные варианты. Arc-код существует; наличие реализации не означает её активацию. Параллельная правка убирает `arc_clamped` из player CLI, сохраняя низкоуровневые эксперименты.
- `-Measure` не передан. Его скрипт использует ROS2 runtime, поэтому его p95 нельзя подписывать как latency данного direct-плеера.
- Python Stage 3 baseline, старые Stage 2 JS detector/geometry и их YAML не составляют текущий вычислительный путь.
- YOLO/Ultralytics, Random Forest, LightGBM, CUDA, карта, deskew, ICP-одометрия, tracking, TTC и синтетический генератор не участвуют в данном кадре. Генератор и исследования движения существуют отдельно.
- Важная оговорка: stream CLI пока **вычисляет и legacy-, и model-ветку**, хотя активный выход — model_v1. Это лишняя работа и причина некорректной интерпретации таймеров, а не переключение сигнала на legacy.

## Предусловия и места ожидания

Launcher проверяет существование `artefacts/stage_3/cpp_envelope_core/fastdds_udp_smoke.xml` и `artefacts/stage_4/cpu_viewer/vendor/three.min.js` **до сборки образа**, даже для direct_cpp. HTTP также отдаёт `OrbitControls.js`. Всё это находится в ignored `artefacts`; vendor создаётся [export_cpu_viewer_replay.py](../../../../scripts/export_cpu_viewer_replay.py), 52–59. Ссылка на «предыдущий export» без команды — недостаточная инструкция чистого запуска.

Сервер создаёт все `ArchiveBagFrames` при старте, поэтому требуются оба файла: `dataset/for_hackathon/new_data` и `dataset/for_hackathon/for_hackathon`. Это TAR без расширения; `dataset/README.md` описывает другую, исходную упаковку `.zst`. В образе данные и viewer-артефакты не запечены. Root mount предоставляет данные/web/config, тогда как сервер/C++ берутся из `/app` образа: revision рабочего дерева недостаточно для определения версии уже работающего контейнера.

SQLite извлекается лениво; холодный доступ и переход между частями могут быть существенно дороже тёплого. Cache ограничен тремя кадрами/результатами. `data_lock` и `runtime_lock` сериализуют работу. Устаревший token проверяется после чтения кадра; уже начатое вычисление не прерывается. Поэтому утверждение «нет DDS → нет никаких очередей/ожиданий» неверно. Время HTTP, чтения XYZF и отрисовки не равно `processing_ms` C++.

Stop перед RebuildImage в команде пользователя нужен: сам launcher при уже работающем совпадающем контейнере может вернуть его после сборки нового образа, не заменив процесс.

## Проверки, зрелость и следующий шаг

На работающем сервере manifest подтвердил конфигурацию выше. Существующие два Python-suite дали 11 PASS; команды и границы — в [индексе](index.md). L0 для code trace, L1 для этих узких checks. Код обнаружения и оба адаптера реализованы; проверка нового полного replay, скорости/потерь, чистого развёртывания и независимого качества здесь не выполнена. Стадия — исследовательский прототип.

Mandatory bug discovery выявила прямое противоречие таймеров и кандидата зависания без deadline; также неполный контракт bootstrap. [Ранжирование и минимальные проверки](bug-audit-2026-09-23.md). Следующий минимальный технический шаг — разнести интервалы измерений и путь выбранного фильтра; остаточный риск — принимать лишние вычисления/чтение архива за проблемы DDS либо за медленную модель.
