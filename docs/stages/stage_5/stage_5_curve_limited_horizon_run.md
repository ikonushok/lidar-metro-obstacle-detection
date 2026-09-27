# Криволинейное продолжение оси с ограниченным горизонтом — результат

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Эксперимент/справка вне запуска direct_cpp+tangent+model_v1. Включение требует отдельной проверки эффекта и регрессии; результаты не меняют runtime default.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Дата: 2026-09-23. Этап 5. Scope: [task spec](stage_5_curve_limited_horizon.md).

## Что изменено

- Исправлена текущая документация: default runtime не останавливает envelope на последней наблюдаемой паре. Он добавляет одну synthetic пару вдоль последней касательной до `rail_forward_max_m`; observed support и continuation публикуются раздельно.
- В C++ core добавлен не-default `arc_limited`: окружность строится через последние три центра **наблюдаемых** пар, а synthetic пары дискретизируют дугу с шагом последнего наблюдаемого station interval. Продолжение ограничено `min(arc_extension_horizon_m, rail_forward_max_m - observed_support_end_source_s_m)`.
- При нулевом горизонте, конце допустимого диапазона, менее трёх пар или коллинеарной тройке дуга не строится. Tangent fallback в `arc_limited` отсутствует; за observed segments остаётся `UNKNOWN`.
- `forward_extension_method=tangent|arc_limited` и `arc_extension_horizon_m` доступны в ROS node, direct C++ stream, CPU runtime, catalog server и PowerShell launcher. JSON содержит method, requested/applied horizon, sampling step и explicit status.
- Default сохранён: `forward_extension_method=tangent`, `arc_extension_horizon_m=0.0`. Не менялись профиль, margins, frame/TF, units, timestamps, AutoRails thresholds, ROS schemas/QoS, CUDA API, background, temporal policy или `CLEAR` policy.

## Evidence и команды

- `docker run ... g++ -std=c++17 -Wall -Wextra -Werror ... tests/test_curve_envelope_core.cpp ...` — PASS. Проверены дуга, её endpoint, zero horizon, collinear support и clipping: запрос 20 м при доступном 1 м дал synthetic continuation ровно 1 м.
- `docker run ... python3 -m unittest tests.test_run_stage_2_cpu_player tests.test_cpu_catalog_runtime_source_frame -v` — PASS, 10/10. Статические тесты покрывают launcher/runtime forwarding и echo extension configuration.
- `docker run ... colcon ... build --base-paths src/lidar_mosmetro3d_cpp ...` — PASS, Ubuntu 22.04 / ROS 2 Humble, один пакет.
- ROS PointCloud2 smoke на `artefacts/stage_5/raw_new_data/frame_01054.xyzf`, CPU default tangent — PASS: `OBSERVED_CORE_INTRUSION_CANDIDATE`, 16 pairs, `core_count=1304`, `unknown_count=47054`.
- Повторный ROS smoke в отдельном `ROS_DOMAIN_ID=211`, `forward_extension_method=arc_limited`, `arc_extension_horizon_m=12.0` — PASS: `OBSERVED_CORE_INTRUSION_CANDIDATE`, 18 pairs, `core_count=1079`, `unknown_count=48935`. Отдельный DDS domain потребовался, потому что последовательный smoke в одном domain получил устаревший ответ предыдущего node; это не интерпретировалось как результат arc mode.
- Direct C++ stream (путь CPU viewer) на том же сохранённом XYZ — PASS: `forward_extension_method=arc_limited`, `forward_extension_status=ARC_LIMITED_APPLIED`, 15 observed / 18 total pairs, applied horizon 12 м, `safety_decision_permitted=false`.
- Негативный direct C++ stream с одной точкой и `arc_limited/12 м` — PASS: `UNKNOWN/INSUFFICIENT_PAIRED_RAIL_SUPPORT`, method/horizon echo и `forward_extension_status=NOT_EVALUATED`; missing rail support не получает continuation.
- Python-файлы проверены `ast.parse` в контейнере. Попытка `py_compile` в read-only bind mount не записала `__pycache__`; это ограничение команды, не ошибка исходников.

## Safety review

Последовательный safety-review текущим агентом после реализации; не независимый. Вердикт: **PASS_WITH_RISKS** для experimental candidate-only режима.

- `arc_limited` не изменяет observed pairs и не использует межкадровое накопление, TF, deskew или timestamps. Рабочий contract остаётся `hesai_lidar <- hesai_lidar`, единицы и профиль — `ASSUMED`.
- Continuation не добавляет `CLEAR`: `system_status=UNKNOWN`, `safety_decision_permitted=false`; core returns не удаляются и не подавляются.
- Invalid/zero/collinear arc support не переводится в касательную: extension отсутствует, а необслуженная дальняя область не получает membership.
- Максимальная длина continuation ограничена явным requested horizon и `rail_forward_max_m`; C++ test проверяет clipping.

Остаточный риск: окружность по трём последним центрам чувствительна к ошибке AutoRails и не является калиброванной геометрией пути или swept envelope кузова на повороте. CUDA не прогонялась с новым методом; реальная точность оси, FP/FN, дистанция и независимые проезды не измерены.

## Validation review

Последовательный validation-review текущим агентом после safety-review; не независимый. Вердикт: **PASS_WITH_RISKS**.

- **L1**: C++ synthetic contract и unit tests.
- **L3 только для CPU**: Humble build → `curve_envelope_node` → published saved real XYZ frame 1054 → verified JSON, а также matching direct stream CPU viewer path.
- Не заявляются улучшение качества, real-time, safety suitability, CUDA parity или обобщение на иные тоннели/проезды. Параметр `arc_extension_horizon_m` — calibration parameter; его значение 12 м в smoke — только test input, не рекомендуемое runtime значение.

## Следующий минимальный тест

На заранее разделённых development/calibration/held-out целых проездах сравнить `tangent`, `arc_limited` и observed-only: скрыть последние наблюдаемые пары, измерить поперечную ошибку прогнозируемой оси на скрытой опоре отдельно для прямых и поворотов, затем измерить FP/мин, TP/FN и долю `UNKNOWN`. До этого `arc_limited` не включать default и не менять profile/margin.
