# Stage 5: cloud_with_fake_obj current detection check

Дата: 2026-09-25. Режим: `validation/inspect`.

## Задача

- Goal: проверить, выдаёт ли текущее решение детекции на новом positive-containing датасете `dataset/for_hackathon/cloud_with_fake_obj`.
- Наблюдаемая проблема или исходный claim: организаторы передали `cloud_with_fake_obj`; по сообщению пользователя в нём точно есть TP-объекты.
- Non-goals: не менять код, модель, thresholds, geometry/envelope, temporal policy, split или параметры viewer; не использовать датасет для обучения/калибровки.
- Source of truth: фактический архив `dataset/for_hackathon/cloud_with_fake_obj`, текущий поднятый viewer/API на `127.0.0.1:8100`, `scripts/serve_stage_2_cpu_catalog.py`, `src/cpp/curve_pipeline_stream_cli.cpp`, `src/lidar_mosmetro3d_cpp/src/curve_envelope_node.cpp`.
- Этап: stage 5, independent synthetic/fake-object held-out read-only check.
- Целевое окружение: Ubuntu 22.04 + ROS 2 Humble + Docker; фактическая проверка: уже запущенный контейнер `lidar-mosmetro3d:stage-4-cpu-viewer-v2-best`.
- Входные данные: TAR без расширения `dataset/for_hackathon/cloud_with_fake_obj`, source `cloud_with_fake_obj`, 1510 кадров, `hesai_lidar`, 307200 точек на проверенном окне.
- Рабочие frames и transforms: `hesai_lidar <- hesai_lidar`; физическая калибровка и объектные GT-боксы/интервалы от организаторов в репозитории не найдены.
- Режим baseline: `direct_cpp`, `development_candidate`, `candidate_baseline_v2`, `tangent`, rail forward range `2..80 m`.
- Temporal rule: API viewer даёт per-frame direct C++ result; ROS node подтверждает публичный alarm только после 2 последовательных model alarm frames, `UNKNOWN` сбрасывает состояние. Это правило зеркалировано offline по `curve_envelope_node.cpp`.
- Allowed files: этот отчёт и `artefacts/stage_5/cloud_with_fake_obj_current_detection_20260925/*`.
- Files to avoid: runtime source, model export, configs, dataset archive.
- Защищённые контракты: `UNKNOWN != CLEAR`; `safety_decision_permitted=false`; negative model output не доказывает свободный путь; не заявлять object-level recall без GT matching.
- Основной агент: `agents/lidar_obstacle_pipeline.md`.
- Validation reviewer: применён как проверка уровня claim по фактическим командам.
- Validation target: L1 для факта прогона текущего решения на новом датасете; не L3/L4 recall из-за отсутствия GT object matching.
- Acceptance criteria: если текущий ROS temporal-public path детектирует TP, должны быть устойчивые последовательные frame-level candidates на positive interval; одиночный per-frame candidate не считается подтверждённой public detection.

## Отчёт о завершении

- Что изменено: код и параметры не менялись; сохранены компактные артефакты полного покадрового прогона.
- Evidence inspected:
  - `agents/context_router.md`, `agents/lidar_obstacle_pipeline.md`, `agents/validation_reviewer.md`;
  - `scripts/serve_stage_2_cpu_catalog.py`;
  - `src/cpp/curve_pipeline_stream_cli.cpp`;
  - `src/lidar_mosmetro3d_cpp/src/curve_envelope_node.cpp`;
  - API manifest `http://127.0.0.1:8100/api/cpu_sources/cloud_with_fake_obj/manifest.json`;
  - `artefacts/stage_5/cloud_with_fake_obj_current_detection_20260925/summary.json`;
  - `artefacts/stage_5/cloud_with_fake_obj_current_detection_20260925/frames_compact.json`.
- Commands run:
  - `docker images --format ...` / `docker ps --format ...` - найден запущенный `lidar-cpu-catalog-8100-direct_cpp-development_candidate-fmin2-tangent-arc0-r60-turn8-fit5-candidate_baseline_v2` на image `lidar-mosmetro3d:stage-4-cpu-viewer-v2-best`.
  - `Invoke-WebRequest http://127.0.0.1:8100/api/cpu_sources/cloud_with_fake_obj/manifest.json` - PASS; `frame_count=1510`, `runtime_transport=direct_cpp`, `rail_selection_method=development_candidate`, `noise_filter_mode=candidate_baseline_v2`, `safety_decision_permitted=false`.
  - Sequential API sweep `0..1509` через `/api/cpu_sources/cloud_with_fake_obj/<index>.json` - PASS; сохранены `summary.json` и `frames_compact.json`.
  - Focus window `1025..1035` из `frames_compact.json` - PASS; единственный frame-level candidate находится на кадре `1030`, соседние кадры `1029` и `1031` не reportable.
- Result:
  - Всего кадров: `1510`, длительность по bag offsets: `150.851 s`.
  - `CURVE_AXIS_SUPPORTED`: `1494` кадров.
  - `UNKNOWN`: `16` кадров, все с reason `INSUFFICIENT_PAIRED_RAIL_SUPPORT`; интервалы `217..231` и `369`.
  - `NO_REPORTABLE_INTRUSION_NOISE_IGNORED`: `1493` кадров.
  - Per-frame `OBSERVED_CORE_INTRUSION_CANDIDATE`: `1` кадр, index `1030`.
  - ROS-style causal temporal confirmed alarm: `0` кадров.
  - Кадр `1030`: offset `102.944870033 s`, `reportable_core_count=80`, nearest reportable point at `55.884001 m` from source origin, xyz `[3.090264, -55.797604, 0.315009]`; temporal streak length only `1`.
- Verdict:
  - `BLOCK` для claim "TP-объекты детектируются текущим публичным temporal path": текущий результат не даёт ни одного подтверждённого causal temporal alarm.
  - `PASS_WITH_RISKS` для более слабого claim "геометрический/model per-frame path иногда видит candidate": да, но только один кадр из 1510.
- Validation level achieved: L1. Выполнен полный покадровый прогон одного нового датасета через текущий поднятый runtime/API, но нет object-level GT matching и не выполнен отдельный ROS2 replay именно этого архива.
- Что не проверено:
  - точные GT интервалы/боксы TP-объектов;
  - object-level recall/precision по matching;
  - full ROS2 bag replay этого архива с очередью/drops;
  - визуальная проверка кадра `1030` и соседних кадров.
- Известные FP/FN или safety-риск: датасет заявлен positive-containing, но current temporal-public detector не подтверждает alarm; вероятный FN на fake-object held-out. `UNKNOWN` кадры не являются `CLEAR`.
- Следующий минимальный тест:
  1. Получить или восстановить GT interval/box для fake object.
  2. Визуально проверить кадры вокруг `1030` и фактические TP-кадры в viewer.
  3. Если TP действительно не совпадает с кадром `1030`, запускать bug-reproducer/diagnostic pass по feature/component suppression без изменения порогов до отдельного согласования.
- Residual risk: без GT неизвестно, является ли одиночный candidate на `1030` настоящим TP или FP; тем не менее текущий temporal-public результат на всём датасете равен нулю.
