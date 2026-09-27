# Stage 5 — C++ development candidate: локальная непрерывная ось

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией. Отсутствие экстраполяции относится к выбору observed-пар; текущий runtime затем добавляет tangent-продолжение габарита.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

## Задача

- Goal: добавить в C++ `curve_envelope_node` выбираемый `development_candidate`: локально непрерывную цепочку **наблюдаемых** пар рельсов; передавать её в неизменённый `CurveRailAxis`/envelope checker.
- Наблюдаемая проблема: `DetectAutoRails` выбирает пары через global linear consensus, хотя габарит уже строится по ломаной; на кривой это даёт `UNKNOWN` при существующих локальных парах.
- Первоначальные non-goals: не менять default, профиль/margins/AutoRails numeric config, PointCloud2/TF/time contracts, deskew, карту, tracking, CUDA, правила core/margin/UNKNOWN или схему topic/QoS. Default исключён из non-goals явным решением пользователя после визуального сравнения; прочие ограничения сохранены.
- Source of truth: `src/cpp/auto_rails_core.*`, `src/cpp/curve_envelope_core.cpp`, `src/lidar_mosmetro3d_cpp/src/curve_envelope_node.cpp`, Stage 5 fixed comparison and `docs/README_methodology.md`.
- Этап: 5, восстановление оси и честное сравнение метода.
- Целевое окружение: Ubuntu 22.04 + ROS 2 Humble + Docker; фактическая проверка — локальный образ `lidar-mosmetro3d:stage_3_baseline`.
- Вход: одиночный `PointCloud2` в `hesai_lidar`, source XYZ, единицы `m_ASSUMED`; transform отсутствует и не добавляется (`hesai_lidar <- hesai_lidar`).
- Режим: parameter `rail_selection_method=baseline|development_candidate`, default `development_candidate` (переключено по явному решению пользователя после сравнительного просмотра). При `development_candidate` используются только рельсовые пары, реально отобранные в station bins; при недостатке/неоднозначности — `UNKNOWN`. Историческая запись описывает выбор пар на дату отчёта; текущий envelope runtime отдельно имеет явную synthetic continuation, см. [stage_5_curve_limited_horizon.md](stage_5_curve_limited_horizon.md).
- Allowed files: `src/cpp/auto_rails_core.*`, `src/lidar_mosmetro3d_cpp/src/curve_envelope_node.cpp`, `scripts/cpu_catalog_runtime.py`, `scripts/serve_stage_2_cpu_catalog.py`, `scripts/measure_cpu_catalog_window.py`, `scripts/run_stage_2_cpu_player.ps1`, viewer scripts, узкие C++/CLI тесты, Stage 5 docs/artefacts.
- Files to avoid: YAML профиля, геометрия profile/margins, message types, launch/QoS, CUDA implementation, map/deskew/tracking.
- Защищённые контракты: every core return remains intrusion candidate; `UNKNOWN != CLEAR`; axis/end envelope stop at last observed pair; frame/time and profile bounds unchanged.
- Deliverables: C++ method selector and JSON diagnostic; narrow negative/positive tests; C++ paired replay over the fixed development cases; safety-review then validation-review; после явного принятия — переключённый runtime default.
- Validation target: L1 for offline C++ core/CLI comparison; L0 for ROS2 runtime until Docker Humble build and replay run.
- Acceptance: explicit `baseline` behaviour сохраняется; implicit default воспроизводит explicit `development_candidate`; candidate retains `UNKNOWN` on no support/ambiguity and uses the same envelope implementation and bounds.
- Stop conditions: any need to change thresholds/profile/frame/time, candidate requiring extrapolation/accumulation, or evidence that core returns are suppressed.

## План

1. Реализовать выбор метода в core с локальным DP только по существующим station-pairs; до принятия default был baseline.
2. Передать method параметр в C++ node и публиковать его в JSON, включая `UNKNOWN`.
3. Добавить C++-уровневую проверку candidate/baseline и негативные случаи отсутствия опоры.
4. Прогнать C++ на fixed Stage 5 raw frames, затем отдельно safety-review и validation-review.

## Отчёт о завершении

### Что изменено

- В `auto_rails_core` добавлен `RailSelectionMethod::kDevelopmentCandidate`. Он использует те же station-local pairs, что baseline, и dynamic programming выбирает одну локально непрерывную цепочку. В результирующую ось входят только пары этой цепочки; после последней пары новых точек, сегментов и габарита нет. После принятия default его implicit выбор изменён на candidate; `baseline` остаётся доступным только явным параметром.
- `curve_envelope_node` получил параметр `rail_selection_method` со значениями `baseline` и `development_candidate` (default). Он публикуется в JSON и для успешного, и для `UNKNOWN` результата. Неизвестное значение даёт `UNKNOWN/INVALID_RAIL_SELECTION_METHOD`.
- Изменены CPU catalog/viewer scripts: они передают параметр, проверяют его echo в JSON; viewer показывает метод. Default в этих скриптах теперь `development_candidate`; для сравнений следует передать `-RailSelectionMethod baseline` явно.
- Не менялись profile, margins, числовые AutoRails параметры, frame/TF, timestamps, deskew, карта, tracking, CUDA API, QoS или правила core/margin/UNKNOWN. Для development viewer добавлены раздельные ROS topics по имени метода, чтобы параллельные baseline/candidate не могли забрать ответ друг друга. Default изменён только для выбора пар: `development_candidate`; `baseline` остаётся явной обратимой опцией.

### Evidence и результаты

Фиксированный C++ replay (5 повторов; те же raw XYZ и bounds) воспроизводит offline-парное различие. На 1054 и 10000 baseline даёт `UNKNOWN/NO_STRAIGHT_CONSISTENT_PAIR`, а candidate — соответственно 16 пар, `core=514`, `UNKNOWN=84517`; и 15 пар, `core=451`, `UNKNOWN=82732`. На 0/1150 candidate увеличивает число пар с 13 до 14 и с 10 до 11; на 5500, doubleT 168/55/160 результат не хуже baseline и совпадает по `core`/`UNKNOWN` там, где пары совпали. Это development evidence, не precision/recall и не абсолютная калибровка оси.

Узкий C++ тест на 1054 после переключения подтвердил равенство implicit default и explicit `development_candidate`; явный `baseline` на этом кадре сохранил `UNKNOWN/NO_STRAIGHT_CONSISTENT_PAIR`. Candidate имеет 16 строго упорядоченных пар с gap не более текущего `max_gap`; одна точка без пары и невалидный method остаются `UNKNOWN`.

### Выполненные команды

```powershell
node --test tests/test_stage_5_rail_axis_experiment.cjs tests/test_live_envelope.cjs
docker run --rm -v "${PWD}:/workspace" -w /workspace lidar-mosmetro3d:stage_3_baseline sh -lc 'g++ -std=c++17 -O2 -I src/cpp src/cpp/auto_rails_selection_test.cpp src/cpp/auto_rails_core.cpp src/cpp/curve_envelope_core.cpp -o /tmp/auto_rails_selection_test && /tmp/auto_rails_selection_test artefacts/stage_5/raw_new_data/frame_01054.xyzf'
docker run --rm -v "${PWD}:/workspace" -w /workspace lidar-mosmetro3d:stage_3_baseline sh -lc '. /opt/ros/humble/setup.sh && colcon --log-base /tmp/stage5_final_log build --base-paths src/lidar_mosmetro3d_cpp --build-base /tmp/stage5_final_build --install-base /tmp/stage5_final_install && . /tmp/stage5_final_install/setup.sh && python3 tests/smoke_curve_envelope_node.py --xyzf artefacts/stage_5/raw_new_data/frame_01054.xyzf --backend cpu --rail-selection-method development_candidate'
```

Результаты: Node tests 10/10; C++ unit `PASS`; ROS 2 Humble package собран в temporary prefix; ROS smoke на 1054: `OBSERVED_CORE_INTRUSION_CANDIDATE`, `rail_pair_count=16`, `core_count=514`, `unknown_count=84517`, method `development_candidate`. Negative smoke с одной исходной точкой: `UNKNOWN`, zero pairs/core, `unknown_count=1`.

Локальная визуальная проверка после интеграции: существующий `http://localhost:8099/` оставлен baseline. Изолированный candidate доступен на `http://localhost:8100/`; `manifest.json` подтвердил `development_candidate`. HTTP replay `api/cpu_new_data/1054.json` вернул `rail_selection_method=development_candidate`, `CURVE_AXIS_SUPPORTED`, 16 пар, `core=514`, `UNKNOWN=84517`, вычисление core 89.43 ms. До разнесения topics API корректно отклонял несовпадающий method echo вместо показа результата другого метода; после разнесения проверка прошла.

### Safety-review (последовательный проход текущего агента; не независимый)

**PASS_WITH_RISKS.** Проверены инварианты: candidate не меняет profile/margins/frame/time; использует только отобранные observed pairs; `AnalyzeCurveEnvelope` остаётся единым checker; любое попадание в core остаётся candidate; отсутствие пары, недостаточная/неоднозначная цепочка и невалидный выбор метода дают `UNKNOWN`, не `CLEAR`. Endpoint envelope ограничен последней парой, потому что `CurveEnvelope` строит сегменты только между возвращёнными парами. Разделение viewer topics предотвращает смешение результата baseline и candidate; несовпадающий echo метода — fail-closed HTTP error.

Остаточный risk: локальная цепочка может выбрать не-рельсовую геометрию, если она проходит исходные eligibility thresholds; абсолютная точность оси на кривой не калибрована. CUDA path принимает те же pairs, но candidate через CUDA не прогонялся. Это запрещает safety/production claim, но не отменяет явно принятое переключение development default.

### Validation-review (последовательный проход после safety-review; не независимый)

**PASS_WITH_RISKS, L3 только для CPU ROS2 smoke на сохранённом real frame 1054.** Есть успешные C++ compile/unit, Humble `colcon build`, публикация реального saved XYZ как `PointCloud2`, автоматическая проверка JSON и отдельный negative input. L3 не переносится на bag replay, CUDA, иной frame, иной поезд или production latency. Fixed eight-frame C++ replay поддерживает только development comparison; независимых проездов, ground truth оси и TP/FP/FN нет.

### Переключение default (явное решение пользователя)

Изменены implicit defaults C++ core, ROS node, CLI, CPU catalog/export/measurement scripts, PowerShell launcher и ROS smoke: `development_candidate`. Явный `baseline` сохранён для rollback и comparisons. После этого выполнены:

```powershell
node --test tests/test_stage_5_rail_axis_experiment.cjs tests/test_live_envelope.cjs
docker run --rm -v "${PWD}:/workspace" -w /workspace lidar-mosmetro3d:stage_3_baseline sh -lc 'g++ -std=c++17 -O2 -I src/cpp src/cpp/auto_rails_selection_test.cpp src/cpp/auto_rails_core.cpp src/cpp/curve_envelope_core.cpp -o /tmp/auto_rails_selection_test && /tmp/auto_rails_selection_test artefacts/stage_5/raw_new_data/frame_01054.xyzf'
docker run --rm -v "${PWD}:/workspace" -w /workspace -e FASTRTPS_DEFAULT_PROFILES_FILE=/workspace/artefacts/stage_3/cpp_envelope_core/fastdds_udp_smoke.xml lidar-mosmetro3d:stage_3_baseline sh -lc '. /opt/ros/humble/setup.sh && colcon --log-base /tmp/stage5_default_log build --base-paths src/lidar_mosmetro3d_cpp --build-base /tmp/stage5_default_build --install-base /tmp/stage5_default_install && . /tmp/stage5_default_install/setup.sh && python3 tests/smoke_curve_envelope_node.py --xyzf artefacts/stage_5/raw_new_data/frame_01054.xyzf --backend cpu'
.\scripts\run_stage_2_cpu_player.ps1 -Port 8099 -NoBrowser -RebuildImage
```

Результаты: Node tests 10/10; C++ test `PASS`; Humble build `PASS`; default smoke 1054 вернул `development_candidate`, 16 пар, `core=514`, `UNKNOWN=84517`; HTTP `http://localhost:8099/manifest.json` и `api/cpu_new_data/1054.json` подтвердили тот же method/status. Старый baseline container на 8099 остановлен и заменён новым default container `lidar-cpu-catalog-8099-development_candidate`.

### Safety-review после переключения (последовательный проход текущего агента; не независимый)

**PASS_WITH_RISKS.** Смена default изменяет только выбор существующих пар. Проверены: ось и envelope заканчиваются на последней observed pair; отсутствующая/недостаточная опора остаётся `UNKNOWN`; core returns не фильтруются по классу, повторяемости, карте или неподвижности; profile/margins/frame/time не изменялись. `baseline` доступен только явным параметром, поэтому откат не требует изменения кода.

### Validation-review после переключения (последовательный проход после safety-review; не независимый)

**PASS_WITH_RISKS, L3 только для перечисленного CPU ROS2 saved-frame smoke и локального HTTP viewer 1054.** Новый default доказан в C++ API, ROS parameter default и viewer launch. Это не доказывает качество на независимых поездках, calibrated axis accuracy, CUDA или production readiness.

### Следующий минимальный тест и остаточный риск

Запустить новый default в CPU replay окна 1050–1150 и отдельно на повороте с сохранением JSON/viewer evidence; вручную проверить continuity и конец опоры. Затем повторить на независимом проезде как проверку принятого default. Нельзя включать extrapolation, менять `UNKNOWN` или подавлять инфраструктурные core returns для улучшения картинки.
