# Stage 5 presentation videos

## Задача

- Goal: подготовить пять коротких 5-секундных демо-видео для презентации пайплайна.
- Наблюдаемая проблема или исходный claim: нужны отдельные слои визуализации: raw cloud, rails/axis, envelope до 80 м, warning band +0.5 м, и `doubleT_obstacle` с проходящим человеком.
- Non-goals: не менять runtime detector, C++/ROS2 код, параметры профиля, rail-selection defaults, метрики, датасет и safety contracts.
- Source of truth: сохранённые `.xyzf` кадры и существующие stage 5 визуальные sequence JSON; `config/geometry_contract.yaml` как ASSUMED_HACKATHON visual contract.
- Этап `docs/README_work_plan.md`: Stage 5 demo/release material.
- Целевое окружение: Ubuntu 22.04 + ROS 2 Humble + Docker; фактическая среда проверки: локальный Docker image `lidar-mosmetro3d:stage_3_baseline` для MP4/ffmpeg.
- Входные данные и единицы: source XYZ float32, метры ASSUMED.
- Конкретный bag/версия/интервал: `new_data` сохранённое окно `9995..10005`; `doubleT_obstacle` окно `35..84`.
- Рабочие frames и transforms: source XYZ unchanged; визуальное направление вперёд `-Y`; transforms не применяются.
- Режим baseline/расширений: визуальный overlay only. Envelope/warning band строятся из сохранённых rail-pair/path-profile точек и ASSUMED_HACKATHON half-widths; `CLEAR/NO_OBSTACLE` не публикуется.
- Allowed files: `scripts/render_presentation_videos.py`, `docs/stages/stage_5/stage_5_presentation_videos.md`, новые файлы в `artefacts/stage_5/presentation_videos_20260925/`.
- Files to avoid: runtime C++/ROS2, configs, исходные датасеты, существующие артефакты.
- Защищённые контракты: `UNKNOWN != CLEAR`; `safety_decision_permitted=false`; no dataset mutation; no calibration claim.
- Deliverables: пять MP4 и `manifest.json`.
- Основной агент: текущий по `agents/lidar_obstacle_pipeline.md`.
- Safety-review: отдельный проход не нужен, потому что runtime/safety logic не меняется; геометрия помечена visual-only.
- Validation-review: нужен финальный проход по наличию файлов, длительности и manifest.
- Validation target: L1 для локально созданных presentation artifacts.
- Validation method: py_compile renderer; запуск renderer в Docker; проверка MP4 через `ffprobe`/размеры файлов/manifest.
- Acceptance criteria: 5 MP4 в `artefacts`, каждая около 5 секунд, manifest содержит исходные окна и `safety_decision_permitted=false`.
- Stop conditions: отсутствует MP4 encoder или сохранённые кадры.

## Отчёт о завершении

- Что изменено: добавлен offline renderer `scripts/render_presentation_videos.py`; создана папка `artefacts/stage_5/presentation_videos_20260925/` с пятью MP4, preview PNG и `manifest.json`.
- Evidence inspected: `agents/context_router.md`, `agents/lidar_obstacle_pipeline.md`, `agents/validation_reviewer.md`; saved frame exports `artefacts/stage_5/raw_new_data_visual_windows/*.xyzf`; sequence `artefacts/stage_5/rail_axis_video_compare/window_10000.json`; `artefacts/stage_2/player_doubleT_obstacle/manifest.json`; preview frames from generated MP4.
- Commands run:
  - `docker run --rm ... python3 -m py_compile scripts/render_presentation_videos.py` — PASS.
  - `docker run --rm ... python3 scripts/render_presentation_videos.py --output-dir artefacts/stage_5/presentation_videos_20260925 --fps 10 --seconds 5 --sample-max 90000` — PASS, 5 MP4 created.
  - `docker run --rm ... ffprobe ... presentation_videos_20260925/*.mp4` — PASS: every MP4 is 1280x720, 50 frames, 5.000000 seconds.
  - `docker run --rm ... ffmpeg -ss 2.5 ... previews/*_mid.png` — PASS; middle preview frames created and visually checked.
- Validation level achieved: L1 for local presentation artifacts. The files exist, encode correctly, and representative frames show non-empty point clouds and expected overlays.
- Что не проверено: playback in PowerPoint/target presentation laptop; semantic correctness of all yellow points; calibrated physical clearance; full-motion source beyond the saved 11-frame `new_data` visual window.
- Известные FP/FN или safety-риски: warning band is visual-only ASSUMED_HACKATHON geometry; it is not an obstacle metric, not `CLEAR/NO_OBSTACLE`, and not a safety decision.
- Следующий минимальный тест: open the five MP4 in the actual presentation tool and confirm readability after slide compression/export.
- Residual risk: `new_data` video uses saved frames `9995..10005` expanded to 5 seconds for presentation timing; it is not a fresh full-bag replay.

## Обновление — перспективный ракурс для HTML-презентации

- Goal: заменить неудачные top-view ролики на фронтальный перспективный ракурс по пользовательским reference screenshots.
- Источники: предоставленные screenshots; `docs/README_methodology.md`; `artefacts/stage_5/rail_axis_video_compare/window_10000.json`; `artefacts/stage_2/player_doubleT_obstacle/manifest.json`; `config/obstacle_annotations_development.json`.
- Deliverables: screenshots in `docs/presentation/picts/`; five 5-second MP4 clips in `docs/presentation/movies/`; `docs/presentation/movies/manifest.json`.
- Runtime changes: none. Новый renderer `scripts/render_presentation_perspective_videos.py` работает offline по сохранённым `.xyzf` и JSON-профилям.
- Safety contract: visual-only; `safety_decision_permitted=false`; warning band `+0,5 м` is presentation geometry, not a calibrated safety verdict.
- Validation target: L1 for local presentation artifacts: script compiles, renderer completes, MP4 duration/frame count is checked, representative previews are visually inspected.

### Результат обновления

- Что изменено: reference screenshots скопированы в `docs/presentation/picts/`; в `docs/README_methodology.md` добавлена демонстрационная последовательность 1–5; добавлен renderer `scripts/render_presentation_perspective_videos.py`; создан набор MP4 в `docs/presentation/movies/`.
- Видео:
  - `01_tunnel.mp4` — тоннель, только облако точек.
  - `02_rails_axis_distances.mp4` — рельсы, ось, расстояния и направляющие.
  - `03_train_envelope_80m.mp4` — добавлен габарит поезда до 80 м.
  - `04_warning_margin_0p5m.mp4` — добавлены жёлтые точки в слое `габарит + 0,5 м`.
  - `05_doubleT_obstacle_person.mp4` — `doubleT_obstacle`, событие OBS-002 около 56,4 м.
- Commands run:
  - `docker run --rm -v ${PWD}:/workspace -w /workspace lidar-mosmetro3d:stage_3_baseline python3 -m py_compile scripts/render_presentation_perspective_videos.py` — PASS.
  - `docker run --rm -v ${PWD}:/workspace -w /workspace lidar-mosmetro3d:stage_3_baseline python3 scripts/render_presentation_perspective_videos.py --root /workspace --picts-dir /workspace/docs/presentation/picts --movies-dir /workspace/docs/presentation/movies --fps 10 --seconds 5 --sample-max 105000` — PASS.
  - `docker run --rm -v ${PWD}:/workspace -w /workspace lidar-mosmetro3d:stage_3_baseline bash -lc 'for f in docs/presentation/movies/*.mp4; do echo $f; ffprobe ... $f; done'` — PASS: every MP4 is 1280x720, 50 frames, 5.000000 seconds.
- Visual inspection: checked generated previews for `03_train_envelope_80m`, `04_warning_margin_0p5m`, `05_doubleT_obstacle_person`; frames are non-empty and show the intended perspective overlays.
- Validation level achieved: L1 for local presentation artifacts.
- Что не проверено: playback inside the final HTML presentation and browser-specific video compression/rendering.
- Residual risk: overlays remain visual-only ASSUMED geometry; they explain the pipeline but do not prove calibrated clearance or a safety decision.

### Обновление 05 obstacle zoom

- Причина: в первой версии `05_doubleT_obstacle_person.mp4` человек на дальности около 56 м читался слишком мелко.
- Изменение: для `layer == "obstacle"` добавлена отдельная камера, наведённая на OBS-002, с более узким FOV; локальная красная подсветка точек вокруг человека усилена.
- Проверка: `05_doubleT_obstacle_person.mp4` пересобран; `ffprobe` подтвердил 1280x720, 5.000000 seconds, 50 frames; preview `generated_05_doubleT_obstacle_person.png` визуально проверен.
