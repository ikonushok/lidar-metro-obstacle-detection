# Stage 4 — контрольные помехи и принадлежность габариту

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией. Каталог/контракт matching JSON переиспользуется, но прежний ROS transport и timings не описывают direct-плеер.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Дата: 2026-09-22. Режим: patch → safety-review → validation. Этап 4 — демонстрация результата на видео/в плеере.

## Задача

- Goal: перейти от семантики «люди» к общей семантике «помеха» и сделать в CPU viewer явной проверку двух пользовательских контрольных помех `OBS-002`/`OBS-003` относительно результата C++ габарита.
- Наблюдаемая проблема: общий статус кадра показывал наличие любых `CORE`-возвратов, но не отвечал, относится ли к ним именно выбранная контрольная помеха.
- Non-goals: менять AutoRails/CurveRailAxis, профиль, margin, thresholds, TF/оси/единицы, raw XYZ, подавлять инфраструктуру, экстраполировать путь, включать tracking/TTC или выдавать `CLEAR`.
- Source of truth: `doubleT_obstacle`, исходные точки кадров 55/160, пользовательские anchors `OBS-002`/`OBS-003`, matching C++ JSON.
- Frames: `hackathon_track_lidar_livox <- lidar_livox` только как существующий `ASSUMED_HACKATHON` identity-контракт; единицы `m_ASSUMED`.
- Временная база: header timestamp используется только для identity; bag/header clocks не смешиваются.
- Allowed files: отдельная generic obstacle-аннотация, evaluator/viewer wiring, узкие tests, этот отчёт.
- Protected contracts: аннотации не являются входом детектора; `UNKNOWN != CLEAR`; любые наблюдаемые `CORE`-возвраты остаются помехами-кандидатами независимо от класса и размера.
- Основной агент: `lidar_obstacle_pipeline`; затем отдельные последовательные safety- и validation-проходы текущего агента.
- Validation target: L3 для Docker → raw archive → C++ → HTTP → browser на двух выбранных development-кадрах; L1 для принадлежности сохранённых anchors исходным облакам. Физическая калибровка габарита не заявляется.
- Acceptance: UI использует слово «помеха», показывает `CORE_INTERSECTION`, `MARGIN_INTERSECTION`, `OBSERVED_OUTSIDE_GABARIT` или `UNKNOWN` для точной исходной точки; API явно фиксирует `review_annotations_are_detector_input=false`.
- Stop conditions: не продолжать ось за наблюдаемыми парами рельсов и не переводить контрольную помеху в `CORE` по одной ручной отметке.

## Что изменено

- Добавлен canonical evaluator-файл `config/obstacle_annotations_development.json`: два source-return anchors названы контрольными помехами, семантический класс предмета не используется.
- CPU catalog HTTP добавляет подходящую кадру контрольную разметку только после выполнения C++ runtime и явно возвращает `review_annotations_are_detector_input=false`.
- Viewer находит точный source index контрольной точки и сопоставляет его только с C++ `core_source_indices`, `margin_source_indices` и `outside_reference_source_indices`. Контрольная точка отображается и получает отдельный статус; она не меняет общий результат кадра.
- Активные evaluator/tests переведены на generic obstacle config. Исторические документы и прежний `person_annotations_development.json` сохранены для воспроизводимости старых отчётов.
- Обнаружен и устранён operational blocker: работавший на порту 8099 контейнер содержал старый образ и возвращал `UNSUPPORTED_SOURCE_FRAME` для `lidar_livox`. Образ пересобран из текущего workspace, сервер перезапущен.

## Результат на контрольных кадрах

| Событие | Кадр | Точная точка найдена | Поддержанная ось C++ | Общий статус кадра | Статус контрольной помехи |
|---|---:|---|---|---|---|
| `OBS-002` | 55 | source index `179546` | 4–44 м* | `OBSERVED_CORE_INTRUSION_CANDIDATE`, 1009 core returns | `UNKNOWN` — помеха находится дальше конца поддержанной оси |
| `OBS-003` | 160 | source index `145629` | 4–36 м* | `OBSERVED_CORE_INTRUSION_CANDIDATE`, 960 core returns | `UNKNOWN` — помеха находится до начала поддержанной оси |

Общий warning обоих кадров относится к другим наблюдаемым возвратам внутри поддержанного габарита. Он не доказывает попадание `OBS-002`/`OBS-003` в габарит. Нельзя использовать ближайшие 4.24/4.38 м как расстояние до этих контрольных помех.

## Выполненные проверки

- Docker image `lidar-mosmetro3d:stage-4-cpu-viewer` пересобран: ROS 2 Humble package/`colcon build` — PASS; сервер 8099 запущен.
- Python contract tests: 7/7 PASS, включая evaluator-only generic obstacle annotations и source-frame runtime wiring.
- Node unit tests: 17/17 PASS; сохранены singleton/low obstacle, границы `CORE/MARGIN/UNKNOWN`, raw immutability и независимость детектора от annotations.
- Sample replay 0/55/100/160/200 — PASS: оба anchors точно принадлежат исходным component indices; оба остаются `UNKNOWN`; source mutations 0.
- HTTP/API — PASS: кадры 55/160 имеют `lidar_livox`, корректные header identities и `review_annotations_are_detector_input=false`.
- Browser — PASS: на кадрах 55 и 160 видны `OBS-002/OBS-003: контрольная помеха · принадлежность габариту UNKNOWN`; общий C++ warning показан отдельно.
- `git diff --check` по затронутым файлам — PASS.

## Safety-review

`PASS_WITH_RISKS` для проверочного слоя. Аннотации загружаются сервером отдельно и добавляются только после C++ результата; C++ node и геометрия не получают event ID, координаты или номера контрольных кадров. Положительные `CORE`-возвраты не фильтруются. Неподдержанный участок остаётся `UNKNOWN`, а не `OUTSIDE` или `CLEAR`.

## Validation-review

`PASS_WITH_RISKS`, L3 только для описанного локального Docker → C++ → HTTP → browser пути на двух development-кадрах. Claim «в записи есть две пользовательски подтверждённые помехи, и их точные source points отображаются» подтверждён. Claim «обе помехи находятся внутри проверенного габарита» — `HOLD`: текущая ось не покрывает их продольные позиции, а frame/profile остаются `ASSUMED_HACKATHON`.

## Следующий минимальный тест

Для `OBS-002` нужны наблюдаемые пары рельсов либо внешний путь за 44 м до области около 56 м. Для `OBS-003` нужна проверенная ближняя геометрия от лидара до 4 м. После этого повторить тот же exact-source-index evaluator. До появления такой опоры не экстраполировать габарит ради положительного результата.

Остаточный риск: общие core-кандидаты в этих кадрах могут быть штатной инфраструктурой; без полной разметки и доверенной геометрии TP/FP/FN и качество детекции не установлены.
