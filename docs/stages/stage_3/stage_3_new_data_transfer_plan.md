# Перенос покадрового baseline на new_data

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Дата: 2026-09-20. Режим: inspect → patch → development validation, этап 3.

- Goal: проверить геометрию короткой выборки new_data и выполнить отдельный эксперимент с существующим покадровым baseline.
- Авторизация: пользователь согласовал предложенный перенос на короткий движущийся участок («го»).
- Non-goals: карта, deskew, tracking, вычитание фона, изменение первого профиля, полная калибровка, quality/real-time/safety claims.
- Источники: agents/context_router.md, lidar_obstacle_pipeline.md, safety_geometry_reviewer.md, validation_reviewer.md; docs/README_methodology.md §5, docs/README_dataset_audit.md, docs/README_work_plan.md этап 3; фактические код, config, new_data и motion artifacts.
- Требование проекта: кандидаты препятствий, ближайшее расстояние, диагностика в Ubuntu 22.04 / ROS2 Humble / Docker. Это offline development-перенос, не приёмка ТЗ или ROS2 end-to-end.
- Вход: TAR dataset/for_hackathon/new_data, PointCloud2 /lidar_points, ожидаемый frame hesai_lidar. Конкретный интервал выбрать по доступной диагностике движения и визуальному просмотру, зафиксировать до baseline-прогона.
- XYZ сохраняются в source frame, без переименования облака или применения несуществующей калибровки. Любой новый профиль — явная гипотеза ASSUMED_HACKATHON; оси/единицы/положение проверяются визуально, не объявляются поверенными.
- Время: bag/header отдельно; вычисления time.perf_counter. Диагностика ICP не используется как одометрия, deskew или proof скорости поезда.
- Поток: bounded archive window → исходный PointCloud2 → input validation → отдельная гипотеза геометрии → существующий покадровый baseline → JSONL/сводка/проекции.
- Allowed files: новый config/geometry_new_data_experiment.yaml, scripts/experiment_new_data_baseline.py, scripts/replay_new_data_visual.cjs, scripts/render_new_data_transfer.py, узкие тесты профиля; минимальная поддержка явно заданного identity-профиля в src/stage_3_baseline.py, если потребуется. Артефакты artefacts/stage_3/new_data_transfer/. Отдельный отчёт stage_3_new_data_transfer_run.md.
- Files to avoid: raw/archive, старые manifests, исходный config/geometry_contract.yaml, полный motion-анализ и его результаты, старые labels.
- Защищённые контракты: UNKNOWN != CLEAR; safety/clear запрещены; нет фильтра пола/рельсов; без накопления; отсутствие геометрии/неожиданный frame не запускает расчёт. Пороги кластеризации и размеры профиля наследуются явно как непроверенные на new_data.
- План проверки: небольшие raw-проекции; unit tests на новый source frame, чужой frame, неверный transform/оси, низкое препятствие/границы; offline прогон короткого интервала со счётчиками и p95. Нет разметки → не считать recall/FP.
- Роли: текущий агент, отдельные последовательные safety- и validation-проходы; независимость не заявляется.
- Target: L1 для узких тестов и выбранного offline-интервала.
- Stop: неизвестная ориентация → только raw/UNKNOWN; несогласованная геометрия → не включать рабочий профиль; исключения декодирования → остановка, без пустого CLEAR.
- Остаточный риск: монтаж, единицы, путь и motion distortion не имеют внешней калибровки; слабая геометрия тоннеля может давать ложное ICP-совмещение.
- Следующий минимальный тест: декодировать начало/середину/конец выбранного интервала, сравнить XY/YZ/XZ, затем запускать baseline.
