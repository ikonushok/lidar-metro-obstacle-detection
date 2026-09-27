# Stage 5: model_v1 GPU candidate timing

## Задача

- Goal: разложить latency `model_v1` filter на извлечение CORE, поиск компонент, признаки/решение дерева и финализацию, чтобы понять, есть ли практический кандидат на GPU.
- Наблюдаемая проблема или исходный claim: текущий lean benchmark даёт p95 `common_processing_ms=47.9`, `model_noise_filter_ms=73.8`, но не показывает, какая часть model filter пригодна для GPU.
- Non-goals: менять геометрию, пороги, модель, output contract обычного runtime, CUDA backend или ROS2 node.
- Source of truth: текущий C++ код `src/cpp/curve_envelope_core.*`, stream CLI, `scripts/benchmark_lean_noise_model.py`, `docs/README_noise_classifier.md`.
- Пункт/раздел ТЗ и обязательный результат: performance evidence для финального описания экспериментов; числового лимита задержки в ТЗ не заявлять.
- Этап docs/README_work_plan.md: Stage 5 / model_v1 runtime.
- Целевое окружение: Ubuntu 22.04 + ROS 2 Humble + Docker; фактическая среда проверки: Docker image на локальной Windows host.
- Входные данные и единицы: XYZ float32, метры ASSUMED; вычислительная задержка — monotonic steady clock.
- Конкретный bag/версия/интервал, топик и объём выборки: `new_data`, первые 5 минут bag-time, тот же scope что lean benchmark.
- Факты из docs/README_dataset_audit.md, подтверждения на текущем входе и непроверенные предположения: вход не является независимой полной валидацией качества; все поддержанные кадры `new_data` временно считаются отрицательными только для FP-счётчика.
- Рабочие frames и направление transforms: source XYZ frame-local; новых transform нет.
- Режим baseline/расширений; необходимые TF/движение/карта/габарит и поведение при их отсутствии: `development_candidate`, tangent, `model_v1`; `UNKNOWN` не превращается в `CLEAR`.
- Временная база событий и способ измерения вычислительной задержки: `std::chrono::steady_clock` внутри C++ filter; bag offset только для окна выборки.
- Allowed files: `src/cpp/curve_envelope_core.*`, `src/cpp/curve_pipeline_stream_cli.cpp`, `scripts/benchmark_lean_noise_model.py`, новый узкий скрипт/артефакты, этот отчёт.
- Files to avoid: параметры геометрии/порогов, ROS2 message/QoS, датасет, CUDA implementation.
- Защищённые контракты: `UNKNOWN`, safety decision false, CORE membership, model_v1 thresholds and indices.
- Deliverables и статус каждого: profile counters — done; 5min timing summary — done; GPU recommendation — done; CPU spatial-index optimization — done.
- Путь отчёта этапа или категории: `docs/stages/stage_5/stage_5_model_v1_gpu_candidate_timing.md`.
- Основной агент: `agents/lidar_obstacle_pipeline.md`.
- Нужен ли `safety_geometry_reviewer` и почему: нет, изменения диагностические и не меняют геометрию/решения.
- Нужен ли отдельный этап `validation_reviewer`; порядок и кто выполняет проходы: текущий агент проверяет evidence; не заявлять независимое review.
- Validation target: L1 для диагностических таймеров на bounded replay.
- Validation method: C++ compile/unit smoke и Docker lean benchmark с profile flag.
- Acceptance criteria: обычный output сохраняет решения; профиль показывает p95/mean по этапам и counters; вывод явно отделяет CPU profiling от доказательства GPU speedup.
- Stop conditions: если сборка/данные недоступны, зафиксировать read-only вывод по коду без численного claim.

## Отчёт о завершении

- Что изменено: добавлен optional `FrozenNoiseTreeV1Profile` в `ApplyFrozenNoiseTreeV1`; `curve_pipeline_stream_cli` получил диагностический флаг `--profile-model-filter`; `scripts/benchmark_lean_noise_model.py` теперь умеет сохранять summary по внутренним стадиям фильтра. Затем `ApplyFrozenNoiseTreeV1` переведён с полного перебора CORE-точек на spatial hash / voxel grid: ячейка равна `connectivity_radius_m`, соседство ищется только в 27 соседних ячейках, финальный критерий расстояния остался прежним `dx²+dy²+dz² <= radius²`.
- Evidence inspected: `agents/context_router.md`, `agents/lidar_obstacle_pipeline.md`, `agents/task_spec_short.md`; `src/cpp/curve_envelope_core.cpp/.hpp`; `src/cpp/curve_pipeline_stream_cli.cpp`; `scripts/benchmark_lean_noise_model.py`; `Dockerfile`; `docs/README_noise_classifier.md`. В коде `ApplyFrozenNoiseTreeV1` дерево v1 — два условия по `z_extent` и `point_count`; дорогая часть — наивный поиск компонент с проходом по всем непосещённым CORE точкам.
- Commands run: `docker run --rm ... mkdir -p artefacts/stage_5/model_v1_gpu_candidate_timing/bin` — PASS; `g++ -std=c++17 -O2 -Wall -Wextra -Werror ... tests/test_curve_envelope_core.cpp ...` — PASS; `python3 -m py_compile scripts/benchmark_lean_noise_model.py` — PASS; `g++ -std=c++17 -O2 -Wall -Wextra -Werror ... curve_pipeline_stream_cli.cpp ...` — PASS; `.../test_curve_envelope_core` — PASS; O2 5-min benchmark — PASS, 3000 frames, `UNKNOWN=29`, `FP=129`, `processing_p95_ms=18.195893`, `common_processing_p95_ms=14.546178`, `model_noise_filter_p95_ms=4.674152`; O0/default-like CLI compile — PASS; O0 5-min benchmark — PASS, 3000 frames, `UNKNOWN=29`, `FP=129`, `processing_p95_ms=116.955339`, `common_processing_p95_ms=46.972932`, `model_noise_filter_p95_ms=72.792526`. После spatial-index оптимизации: `g++ -std=c++17 -O2 -Wall -Wextra -Werror ... test_curve_envelope_core.cpp ...` — PASS; `g++ -std=c++17 -Wall -Wextra -Werror ... curve_pipeline_stream_cli.cpp ... -o curve_pipeline_stream_cli_spatial_O0` — PASS; `.../test_curve_envelope_core_spatial` — PASS; spatial O0 5-min benchmark — PASS, 3000 frames, `UNKNOWN=29`, `FP=129`, `processing_p95_ms=49.907220`, `common_processing_p95_ms=47.031088`, `model_noise_filter_p95_ms=3.842542`; `python3 -m py_compile scripts/compare_stream_model_outputs.py` — PASS; old O0 vs spatial O0 parity on first 200 `new_data` frames — PASS, exact match on status/counts/reportable/ignored/model index arrays.
- Docker load note: во время замера пользователь указал, что подняты 2 Docker container; read-only `docker stats` подтвердил примерно `99%` и `66%` CPU на двух `lidar-mosmetro3d:timing-fix` контейнерах. Ничего не останавливал. Перед spatial benchmark были активны `stage-4-cpu-viewer` и `timing-fix`; read-only `docker stats` показывал примерно `45%` и `100%` CPU, поэтому абсолютный p95 spatial benchmark также загрязнён фоновой нагрузкой.
- Validation level achieved: **L1** для диагностического CPU profiling на bounded first-5-min `new_data` replay в Docker. Это не end-to-end ROS2 realtime validation.
- Что не проверено: GPU speedup не реализован и не измерен; нет clean isolated-host benchmark без фоновой Docker-нагрузки; нет полного `colcon` rebuild с явным `CMAKE_BUILD_TYPE=Release`; нет full 7-source rerun.
- Известные FP/FN или safety-риски: FP count на окне остался `129`; profiling не меняет смысл `UNKNOWN` и не разрешает safety decision; риск подавления малых/низких препятствий самой моделью v1 не менялся.
- Следующий минимальный тест: собрать Docker/colcon в Release и повторить тот же benchmark на свободном host; расширить parity check до полного 5-min окна или полного набора; затем рассмотреть перенос той же spatial-index идеи в legacy filter, если он снова понадобится.
- Residual risk: GPU полезен не для decision tree. В O0/default-like profile до оптимизации `connected_components_and_features_p95_ms=72.125358` из `model_noise_filter_p95_ms=72.792526`; `tree_decision_p95_ms=0.008493`. Spatial index снизил `neighbor_distance_checks_p95` примерно с `1609729` до `3672`, а `model_noise_filter_p95_ms` с `72.792526` до `3.842542` на том же 5-min scope. Проверена exact parity на 200 кадрах; полное parity на всех 3000 кадрах ещё не выполнено.
