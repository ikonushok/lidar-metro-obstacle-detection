# Stage 5: ROS2 temporal runtime confirmation

## Задача

- Goal: перенести подавление однокадровых `model_v1` FP в ROS2 runtime output.
- Наблюдаемая проблема или исходный claim: viewer/offline evaluator уже имеют `model_v1 + temporal`, но `curve_envelope_node` публикует `intrusion_candidate_present` покадрово.
- Non-goals: переобучение модели, изменение геометрии envelope/rails, изменение профиля поезда, background/map/tracking/TTC.
- Source of truth: `src/lidar_mosmetro3d_cpp/src/curve_envelope_node.cpp`, `scripts/check_ros_model_pipeline.py`, `docs/README_noise_classifier.md`.
- Этап docs/README_work_plan.md: stage 5, снижение FP и runtime-интеграция model_v1.
- Целевое окружение: Ubuntu 22.04 + ROS 2 Humble + Docker; фактическая среда проверки фиксируется ниже.
- Входные данные и единицы: PointCloud2 XYZ float32 в source frame; расстояния в `m_ASSUMED`.
- Конкретный bag/версия/интервал: `doubleT_obstacle` development replay для регрессии, если Docker/ROS2 доступен.
- Рабочие frames и направление transforms: без TF, габарит применяется в source coordinates; transform не добавляется.
- Режим baseline/расширений: `noise_filter_mode=model_v1` + causal 2-consecutive-frame confirmation в ROS2 publisher.
- Временная база событий: порядок принятых ROS2 сообщений; повтор того же `header_timestamp_ns` не продвигает temporal state.
- Allowed files: ROS2 node, связанные smoke/check scripts, stage 5 documentation.
- Files to avoid: модель/пороги `ApplyFrozenNoiseTreeV1`, геометрия rails/envelope, dataset files.
- Защищённые контракты: `UNKNOWN` не становится `false`; raw/model frame-local сигнал остаётся диагностически видимым; public `intrusion_candidate_present` становится temporal-confirmed по запросу пользователя.
- Deliverables: C++ runtime patch, узкие тесты/проверки, краткий отчёт.
- Основной агент: `agents/lidar_obstacle_pipeline.md`.
- Safety reviewer: нужен, потому что меняется temporal confirmation.
- Validation reviewer: нужен перед claim о работоспособности.
- Validation target: L1 при локальных unit/static проверках; L3 при успешном Docker/ROS2 replay.
- Acceptance criteria: isolated one-frame model alarm не публикует `intrusion_candidate_present=true`; два последовательных новых positive timestamp подтверждают сигнал; `UNKNOWN` остаётся `null` и сбрасывает confirmation; `doubleT_obstacle` не теряется, допустима задержка 1 кадр.
- Stop conditions: необходимость менять модель, геометрию или смысл `UNKNOWN/CLEAR`.

## Отчёт о завершении

- Что изменено: `curve_envelope_node` получил causal temporal confirmation для `model_v1`; публичные `intrusion_candidate_present` и `reportable_intrusion_candidate_present` теперь равны confirmed-сигналу, а сырой покадровый model output публикуется как `model_frame_intrusion_candidate_present`. Повтор того же `header_timestamp_ns` не продвигает state. `UNKNOWN` сбрасывает state и остаётся `null`.
- Evidence inspected: `agents/context_router.md`, `agents/lidar_obstacle_pipeline.md`, `agents/safety_geometry_reviewer.md`, `agents/validation_reviewer.md`, `curve_envelope_node.cpp`, `smoke_curve_envelope_node.py`, `check_ros_model_pipeline.py`, `README_noise_classifier.md`, результаты `artefacts/stage_5/noise_model_eval_temporal_2026_09_23`.
- Commands run:
  - `.\.venv\Scripts\python.exe -m unittest tests.test_ros2_temporal_runtime_contract -v` — PASS, 2/2.
  - `docker build -t lidar-mosmetro3d:ros2-temporal-runtime .` — PASS, C++ package built under ROS 2 Humble.
  - `docker run --rm lidar-mosmetro3d:ros2-temporal-runtime python3 -m unittest tests.test_ros2_temporal_runtime_contract -v` — PASS, 2/2.
  - `docker run --rm --shm-size=512m -e ROS_DOMAIN_ID=17 ... python3 /app/scripts/check_ros_model_pipeline.py --root /workspace --output /output/parity.json` — PASS on all 201 `doubleT_obstacle` frames plus invalid-input checks and original 26-byte PointCloud2 check.
  - `docker run --rm --shm-size=512m -e ROS_DOMAIN_ID=18 ... python3 /workspace/tests/smoke_curve_envelope_node.py --xyzf .../frame_0013.xyzf --backend cpu --noise-filter-mode model_v1` — PASS.
  - `docker run --rm --shm-size=512m -e ROS_DOMAIN_ID=19 ... python3 /app/scripts/check_ros_model_pipeline.py --root /workspace --frames 13` — PASS; isolated model alarm stayed public `candidate=false`.
- Validation level achieved: L3 for ROS2 runtime behavior on the development `doubleT_obstacle` replay; L1 for the explicit isolated-frame suppression check. This is not independent quality validation.
- Что не проверено: seven-source ROS2 replay for runtime causal FP counts; independent positive obstacle; low/small obstacle recall; performance p95 with queue/drops after the temporal change.
- Известные FP/FN или safety-риски: causal filter adds 1-frame public alarm latency. In `doubleT_obstacle`, frame 13 is raw model alarm but public `intrusion_candidate_present=false`; frames 14–64 are public true. This preserves event detection but changes frame-level TP from 52 to 51 for causal ROS2 semantics.
- Следующий минимальный тест: run the same causal ROS2 checker/evaluator over the three FP-heavy negative sources to measure runtime FP reduction, not only offline diagnostic `2-of-3`.
- Residual risk: frame-level confirmation can still confirm adjacent different components; component-level association remains a separate improvement.
