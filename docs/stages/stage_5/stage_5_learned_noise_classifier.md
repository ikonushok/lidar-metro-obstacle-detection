# Обучаемый классификатор компонентов шума — 2026-09-23

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией. Offline здесь относится к истории обучения; интеграция модели в direct и ROS2 уже выполнена.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

## Спецификация

- Goal: собрать первый воспроизводимый offline-классификатор компонентов `CORE`, который заменяемо сравнивается с историческим геометрическим noise-filter.
- Наблюдаемая проблема или исходный claim: старый фильтр применяет жёсткие пороги `22/0.25/1.0/1.2`; пользователь разрешил считать единственный tracked объект в `doubleT_obstacle` препятствием, а все остальные компоненты — шумом.
- Non-goals: не менять frame/TF, envelope, профиль, margin, ROS2 output, safety decision и не объявлять модель доказательством свободного пути.
- Source of truth: пользовательское правило разметки этого эксперимента; `artefacts/stage_2/player_doubleT_obstacle`; текущий C++ stream CLI и `CoreNoiseFilterConfig`.
- Этап: stage 5, offline расширение после baseline.
- Целевое окружение: Ubuntu 22.04 + ROS 2 Humble + Docker; проверка выполняется в существующем Docker image с C++ stream CLI.
- Вход: finite non-zero source XYZ (`float32`, м assumed), 201 кадров `doubleT_obstacle`; frame `lidar_livox`.
- Данные и разметка: положительный непрерывный interval 13--64 включительно. В каждом его кадре положителен только наибольший по числу точек reportable компонент; он соответствует `OBS-002` в кадре 55 (его source-point входит в этот компонент). Остальные, в том числе меньшие reportable компоненты того же кадра, — отрицательные примеры по явному пользовательскому правилу, а не независимая ground truth.
- Режим: envelope и raw `CORE` остаются кандидатом/`UNKNOWN`; модель работает только offline над компонентами, поэтому TF, карта, движение и изменение габарита не требуются.
- Временная база: только monotonic clock процесса для benchmark предсказания; bag/header timestamps не вычитаются.
- Allowed files: этот отчёт, `.gitignore`, `scripts/train_noise_classifier.py`, `tests/test_train_noise_classifier.py`, `models/noise_classifier_doubleT_obstacle_v1.json`.
- Files to avoid: C++ geometry, ROS2 messages, configs габарита, текущий production filter и пользовательские незакоммиченные файлы.
- Защищённые контракты: `UNKNOWN` не становится `CLEAR`; raw CORE и source indices не отбрасываются; отрицательный класс не является доказательством отсутствия препятствия.
- Deliverables: trainer — planned; portable JSON model — planned; test — planned; runtime replacement — not implemented.
- Reviewer: требуется последовательный `safety_geometry_reviewer`, так как будущая модель влияет на подавление кандидатов; затем `validation_reviewer` для evidence.
- Validation target: L1 для точного чтения 201 сохранённых XYZ кадров, формирования модели и узких тестов; качество на независимом положительном проезде не заявляется.
- Acceptance: JSON содержит признаки, дерево, происхождение данных, правило labels и измеренный Python inference benchmark; trainer отклоняет пропущенный positive interval и не перезаписывает существующую модель.
- Stop conditions: несовпадение 201 frame файлов, отсутствие положительных компонентов, попытка применить результат как safety/CLEAR decision или перезаписать модель.

## Отчёт о завершении

- Что изменено: добавлен stdlib-only trainer. Он передаёт каждый XYZ кадр в текущий C++ CLI, строит компоненты raw `CORE` с тем же радиусом 0,25 м, вычисляет восемь геометрических признаков, обучает CART depth <=4 и сохраняет переносимый JSON. Модель не подключена к ROS2/C++ runtime и не изменяет текущий filter. `.gitignore` разрешает track только этого проверяемого model artifact.
- Evidence inspected: 201 source XYZ кадров `doubleT_obstacle`; output текущего CLI; `OBS-002`/кадр 55 как подтверждение соответствия tracked компонента; `CoreNoiseFilterConfig` и предыдущий full scan 13--64.
- Commands run: `docker run ... python3 -m unittest tests/test_train_noise_classifier.py` — PASS; `docker run ... python3 scripts/train_noise_classifier.py --frames-dir ... --stream-cli ... --output models/noise_classifier_doubleT_obstacle_v1.json` — PASS. 19 365 компонентов: 52 obstacle и 19 313 noise. JSON tree depth 2; development fit TP=52, FP=0, FN=0. Python-only p95 предсказания одного уже извлечённого компонента 0,4502 мкс.
- Validation level achieved: L1 для 201 сохранённых кадров, artifact и узкого test; benchmark не включает extraction, C++ inference, ROS2 transport, очередь или drops.
- Safety-review текущим агентом: PASS_WITH_RISKS. Envelope, raw CORE, `UNKNOWN`, geometry и текущий runtime не изменены. У модели нет права выдать `CLEAR`; отрицательное предсказание — лишь offline label. До runtime integration нужны отдельные boundary/low-obstacle тесты и policy для model failure.
- Validation-review текущим агентом: PASS_WITH_RISKS. Fit относится к той же записи, на которой установлены labels; независимого положительного проезда нет, поэтому claim об обобщении, FP rate и выполнении real-time ТЗ отсутствует.
- Что не проверено: другая геометрия тоннеля, другие препятствия, C++ JSON loader/inference, full pipeline p95 и ROS2 replay.
- Известные FP/FN или safety-риски: label rule «всё кроме largest component 13--64 — noise» дан пользователем и не является независимой разметкой. Модель может выучить этот конкретный объект и текущие особенности оси вместо класса препятствий.
- Следующий минимальный тест: экспортировать модель в ограниченный C++ evaluator без изменения decisions; на одинаковом full replay измерить feature extraction + inference и сравнить с historical filter, сохраняя raw CORE/UNKNOWN.
- Residual risk: JSON — offline development artifact; он не годится для safety decision, production или утверждения о быстродействии на стенде ТЗ.
