# Проверка оси пути на последовательностях (Stage 5)

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Дата: 2026-09-20. Режим: validation. Статус: выполняется.

## Задача

- Goal: на одних и тех же связанных raw-кадрах сравнить C++ `baseline` и `development_candidate`, определить границы геометрической опоры впереди и не выдавать её за наблюдаемость свободного пространства.
- Исходный claim: локально непрерывная цепочка расширяет наблюдаемую опору на поворотах; её правильность выбора колеи ещё не подтверждена.
- Non-goals: не менять AutoRails, default, пороги, profile/margin, frame/time-контракты; не добавлять deskew, SLAM, накопление или semantic suppression.
- Source of truth: `AGENTS.md`; `docs/README_work_plan.md`; `docs/README_methodology.md`; `docs/README_dataset_audit.md`; текущие C++ core/node и raw XYZ. Предыдущие отчёты/JSON являются evidence, не ground truth.
- Пункт/этап: этапы 4–5 из `docs/README_work_plan.md`; адресная проверка корректности новой оси до следующих изменений.
- Целевая среда: Ubuntu 22.04 + ROS 2 Humble + Docker. Фактическая проверка: существующий Docker image `lidar-mosmetro3d:stage_3_baseline`, CPU C++ node.
- Вход: `new_data`, raw `float32` source XYZ, `hesai_lidar`; связанные окна 1049–1059 и 9995–10005. Соседние кадры — не независимые проезды. Дополнительно: существующая user-разметка `OBS-002`, `OBS-003` только для membership, а не axis ground truth.
- Frames/transforms: source XYZ без transform; направление движения только operational assumption `s ≈ -Y`, не калибровка. Не выполняются transforms `target <- source`.
- Режим: одинаковые `baseline`/`development_candidate`, C++ `DetectAutoRails` → `AnalyzeCurveEnvelope`, CPU. Габарит строго между observed pairs; отсутствие/разрыв support остаётся `UNKNOWN`.
- Временная база: header identity сохраняется для сопоставления. Вычислительная задержка не измеряется; разделения разных часов нет.
- Allowed files: этот task spec; узкие offline C++ harness/renderer/summarizer; read-only extractor/audit/contact-sheet для named archive bag; `artefacts/stage_5/axis_sequence_validation/`, `artefacts/stage_5/switch_input_audit/`, `artefacts/stage_5/switch_cpp_screen_current_build/`.
- Files to avoid: runtime C++/ROS2 code, configs/defaults, profile/margins, dataset source и существующие артефакты.
- Защищённые контракты: `UNKNOWN != CLEAR`; каждый core return — candidate; source frame/units неизменны; no extrapolation; viewer только показывает C++ JSON.
- Deliverables: manifest кадров и hashes; C++ JSON baseline/candidate; таблица support/переключений/пересечений; независимые markups либо явный дефицит; C++ visual samples; итоговый report.
- Основной агент: текущий агент по `agents/lidar_obstacle_pipeline.md`.
- Safety-review: да, поскольку анализируется геометрический envelope и interpretation support.
- Validation-review: да, после safety-review; оба прохода выполняет текущий агент последовательно, не независимые.
- Validation target: L2 для статической/mежфайловой проверки плюс L3 только для воспроизведённого CPU ROS2 saved-frame replay, если он успешно пройдёт.
- Validation method: C++ Humble build; replay обоих методов на exact 22 raw frames; проверка hashes, output identity/method, сохранение raw point indices и invariant labels; визуальная сверка selected pairs с raw sections.
- Acceptance: C++ outputs воспроизводимы; границы support и причины UNKNOWN зафиксированы; axis-error публикуется только для независимых source-return marks; отсутствие стрелки/достаточных marks фиксируется явно.
- Stop conditions: отсутствуют windows/raw C++ environment или достаточная независимая rail разметка; в этом случае зафиксировать проверяемый блокер, не придумывая metric.

## Отчёт о завершении

### Что изменено

Runtime, параметры и конфигурации не менялись. Добавлены offline harness `scripts/stage_5_cpp_axis_sequence_validation.py`, renderer `scripts/render_stage_5_cpp_axis_validation.py` и summarizer `scripts/summarize_stage_5_cpp_axis_validation.py`.

Результат: `artefacts/stage_5/axis_sequence_validation/manifest.json`; компактная таблица — `summary/per_frame_comparison.csv`; визуализации — `visuals/`. Harness запускает существующий C++ CPU ROS2 node с `baseline` и `development_candidate`; renderer только рисует его JSON и raw XYZ, не создавая второй detector.

### Evidence и результат

- Версия: commit `11af2a6d3cc0af82109f0d22d95c8bd1a0ee0aa3`; рабочая копия уже была dirty до задачи. Проверяемые runtime sources — текущие `src/cpp/auto_rails_core.cpp`, `src/cpp/curve_envelope_core.cpp`, `src/lidar_mosmetro3d_cpp/src/curve_envelope_node.cpp`.
- Код: `auto_rails_core.cpp` подтверждает: candidate выбирает DP-цепочку observed pairs с `max_gap`; baseline — global linear consensus. `curve_envelope_core.cpp` создаёт сегменты исключительно между соседними парами, без продолжения до/после endpoints. Node публикует rail pairs, axis, exact core indices и `safety_decision_permitted:false`.
- Вход: два связанных development-окна `1049–1059` и `9995–10005`, по 11 кадров; это не независимые проезды. Каждый replayed XYZF содержит finite non-zero returns; исключённые `(0,0,0)` зафиксированы по кадрам. Header identity, raw XYZF SHA-256, method echo и сумма C++ labels проверены для всех 44 запусков.
- Существующая пользовательская разметка `OBS-002/OBS-003` принадлежит `doubleT_obstacle`, а manual rail anchors — кадру 168; она не переносится в `new_data`. Поэтому axis error, TP/FP/FN и event metrics для этих окон **не измерены**. Raw-only сечения без detector overlay подготовлены для кадров 1054/10000 (`s≈6,14,22,30 м`) и требуют по две точные source-return отметки головок рельсов (left/right) на каждое сечение: `visuals/manual_raw_sections/manual_rail_markup_template.json`.
- Стрелка: первичный архивный bag `squareT_platform_squareT_switch` автономно извлечён в `dataset/extracted/squareT_platform_squareT_switch/` и полностью прочитан: 877/877 `PointCloud2`, `/lidar_points`, `hesai_lidar`, 146,663,150 finite non-zero returns, ошибок декодирования и header regressions нет. Имя bag не считается доказательством стрелки. Raw-only XY контакт-лист 37 равномерных фаз и четыре C++-оверлея (включая два расходящихся кадра) не показывают различимой развилки; поэтому **verified switch case не найден**. Это не доказывает, что стрелки нет во всех 877 кадрах: высокодетальный покадровый поиск и независимая разметка не выполнены.

| Окно | baseline support | candidate support | Добавленная candidate опора |
|---|---:|---:|---|
| 1049–1059 | 10/11 | 11/11 | 1054 |
| 9995–10005 | 7/11 | 11/11 | 10000–10003 |

Baseline во всех пяти случаях вернул `MISSING_CURVE_AXIS / NO_STRAIGHT_CONSISTENT_PAIR`; candidate вернул `CURVE_AXIS_SUPPORTED`, `OBSERVED_CORE_INTRUSION_CANDIDATE`. На кадре 1054 поддержанная axis полилиния candidate — 4.0…34.0 м (29.995 м), на 10000 — 4.0…32.0 м (27.770 м). Габарит создан только внутри соответствующих endpoints; максимальный межпарный gap — 2 м на этих двух кадрах. Это не доказательство наблюдаемости всего объёма между/вокруг пар, корректности выбранной колеи или CLEAR. Candidate не вернул `AMBIGUOUS_*`, но output не содержит ranked alternatives, поэтому отсутствие статуса не доказывает отсутствия конкурирующего маршрута.

Покадрово candidate не терял C++ support в обоих окнах; baseline имел два contiguous loss-runs: `[1054]` и `[10000…10003]`. Координатные смещения соседних frame-local осей не трактовались как ошибка пути: движение лидара/transform не установлены.

### Commands run

```powershell
tar -tf dataset/for_hackathon/for_hackathon | Select-String -SimpleMatch 'squareT_platform_squareT_switch'
tar -xOf dataset/for_hackathon/for_hackathon for_hackathon/squareT_platform_squareT_switch/metadata.yaml
docker run --rm ... lidar-mosmetro3d:stage_3_baseline sh -lc '. /opt/ros/humble/setup.sh && colcon ... build ... && python3 scripts/stage_5_cpp_axis_sequence_validation.py --frames-dir artefacts/stage_5/raw_new_data_visual_windows --output artefacts/stage_5/axis_sequence_validation'
docker run --rm ... lidar-mosmetro3d:stage_3_baseline sh -lc 'python3 scripts/render_stage_5_cpp_axis_validation.py ... && python3 scripts/summarize_stage_5_cpp_axis_validation.py ...'
node --test tests/test_stage_5_rail_axis_experiment.cjs tests/test_live_envelope.cjs
docker run --rm ... lidar-mosmetro3d:stage_3_baseline sh -lc 'python3 -m py_compile scripts/stage_5_*axis*validation.py scripts/summarize_stage_5_cpp_axis_validation.py && g++ ... auto_rails_selection_test.cpp ... && /tmp/auto_rails_selection_test artefacts/stage_5/raw_new_data/frame_01054.xyzf'
```

Results: Humble `colcon build` PASS; C++ ROS2 saved-frame replay PASS for 22×2 exact exports; Node tests 10/10 PASS; C++ `auto_rails_selection_test` PASS. The actual complete commands and per-frame data are in the manifest/table; abbreviated commands above are not substitutes for them.

### Safety-review (current agent, sequential; not independent)

**PASS_WITH_RISKS.** Profile `[-1.4,1.4]×[0,3.7]`, 0.5 m margins, source frame and CPU checker were identical for both methods. No class/map/static/temporal suppression occurred: C++ reported every core return as a candidate. Missing baseline axis remained `UNKNOWN`, never CLEAR; candidate did not extrapolate beyond observed first/last pairs. Risks: finite-nonzero export differs from full PointCloud2 by documented zero placeholders; no calibrated geometry, visibility/occlusion, independent rail marks, route identity or switch verification.

### Validation-review (current agent, after safety-review; not independent)

**PASS_WITH_RISKS, L3 only for this saved finite-nonzero CPU C++ ROS2 replay.** Claims are limited to 22 connected development frames and the exact manifest hashes. No held-out run, axis ground truth, event labels, independent route, CUDA, full bag replay, p95 end-to-end latency or production/safety claim exists. The 22 frames must not be treated as 22 trials.

### Следующий минимальный тест / residual risk

One next change to check: **add a diagnostic export of the strongest competing local chain (or fail `UNKNOWN` when it is near-tied), without changing selection/defaults**, then compare it against independent raw-only rail-head marks on 1054/10000 and an extracted, visually verified switch window. Until that evidence exists, the measured improvement is support availability only, not validated route correctness or obstacle-quality improvement.

## Автономное продолжение: архивный bag и недостающий switch case (2026-09-22)

Пользователь явно разрешил продолжать без его разметки и без согласований. Runtime, default, AutoRails параметры, профиль `[-1.4, 1.4] × [0, 3.7]`, margin, frame/time contracts и исходные данные не менялись. Извлечённый bag сохранён; две пустые папки от неуспешных запусков C++ были удалены, успешные artefacts сохранены.

### Что проверено

- `scripts/extract_bag_from_tar.py` извлёк ровно названный `.db3` и `metadata.yaml`; audit прошёл каждое из 877 сообщений в bag-порядке. Это evidence доступности входа, не evidence стрелки или калибровки.
- `scripts/render_bag_raw_contact_sheet.py` построил `artefacts/stage_5/switch_input_audit/stratified_raw_xy_25.png` и manifest: кадры `0,25,...,875,876`, только raw source XY, без AutoRails/CurveEnvelope/detector. В этой разреженной проверке нет наблюдаемой ветви пути.
- `scripts/stage_5_cpp_bag_screen.py` в временно собранном текущем Humble C++ пакете выполнил обе реализации на тех же 37 finite-nonzero source exports. `baseline` получил support в 35/37, `development_candidate` — 37/37. Единственные дополнительные candidate кадры: 500 и 850; оба baseline: `MISSING_CURVE_AXIS/NO_STRAIGHT_CONSISTENT_PAIR`, candidate: 15 observed pairs и support `s=4…34 м` (500) / `s=4…32 м` (850). C++ CORE соответственно 631/625; это кандидаты наблюдаемых попаданий, не obstacle TP.
- Визуализации `artefacts/stage_5/switch_cpp_screen_current_build/visuals/bag_0500_cpp_comparison.png` и `bag_0850_cpp_comparison.png` показывают raw, пары, ось, C++ core-envelope, core returns и support boundaries. Они подтверждают лишь, что локальная цепочка геометрически непрерывна на отображённой прямой коридорной сцене. Они не дают route ground truth, не обнаруживают альтернативную ветвь и не доказывают наблюдаемость/свободу пространства.
- Все восемь требуемых сечений 1054/10000 по-прежнему **без независимых отметок** головок рельсов. Я не подменял этот пробел автоматически выбранными парами либо собственной неоднозначной визуальной оценкой. Следовательно, axis-position error и выбор физически нужной колеи не измерены.

### Воспроизводимость

```powershell
docker run --rm ... python3 scripts/extract_bag_from_tar.py ...squareT_platform_squareT_switch...
docker run --rm ... '. /opt/ros/humble/setup.sh && PYTHONPATH=/workspace/src:/opt/ros/humble/lib/python3.10/site-packages:$PYTHONPATH /usr/bin/python3 scripts/audit_bag.py dataset/extracted/squareT_platform_squareT_switch --output artefacts/stage_5/switch_input_audit'
docker run --rm ... '... render_bag_raw_contact_sheet.py dataset/extracted/squareT_platform_squareT_switch --output artefacts/stage_5/switch_input_audit/stratified_raw_xy_25.png --stride 25 --columns 6'
docker run --rm -e FASTRTPS_DEFAULT_PROFILES_FILE=/workspace/artefacts/stage_3/cpp_envelope_core/fastdds_udp_smoke.xml ... 'colcon ... build --base-paths src/lidar_mosmetro3d_cpp --build-base /tmp/stage5_bag_screen_build --install-base /tmp/stage5_bag_screen_install && . /tmp/stage5_bag_screen_install/setup.sh && ... stage_5_cpp_bag_screen.py dataset/extracted/squareT_platform_squareT_switch --output artefacts/stage_5/switch_cpp_screen_current_build --stride 25'
```

Полные параметры и hashes — в `switch_cpp_screen_current_build/manifest.json`; компактная таблица и status/reason counts — в `summary/`. Контакт-лист и C++ renderer используют source points и сохранённый JSON соответственно; второй detector во viewer не создан.

### Validation-review (current agent, sequential; not independent)

**PASS_WITH_RISKS, L3 только для audit input и paired CPU C++ replay 37 выбранных source exports текущей сборки.** Pycompile обоих новых render/summarize scripts и их фактические artifact runs прошли. Первые C++ попытки с образом без current build/SHM не дали ROS response и не использованы как evidence; итоговый replay собран в отдельном temporary prefix и записал manifest. Нет full-bag C++ replay, external axis GT, всех восьми rail marks, подтверждённой стрелки, ranking альтернативных DP chains, калибровки либо production claim.

### Решение

Подтверждено дополнительно только преимущество availability support: candidate добавляет геометрически ограниченный габарит на 2/37 разреженно выбранных архивных кадрах при неизменённом checker. Корректность физической оси и switch behaviour **не подтверждены**. Единственное следующее изменение по-прежнему: диагностически экспортировать strongest competing local chain либо вернуть `UNKNOWN` при near-tie, не меняя default/пороги; проверять его следует сначала на вручную независимых raw rail-head marks и затем на действительно визуально подтверждённой стрелке.
