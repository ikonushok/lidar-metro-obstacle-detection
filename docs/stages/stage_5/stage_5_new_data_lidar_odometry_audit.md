# Диагностическая LiDAR-одометрия `new_data` — 2026-09-22

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Эксперимент/справка вне запуска direct_cpp+tangent+model_v1. Включение требует отдельной проверки эффекта и регрессии; результаты не меняют runtime default.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

## Задача

- Goal: оценить скорость и пройденную длину `dataset/for_hackathon/new_data` по scan matching, не выдавая оценку за ground truth или вход safety-конвейера.
- Наблюдаемая проблема: `new_data` содержит движущийся LiDAR, но у записи нет одометрии, IMU, TF или external trajectory.
- Non-goals: включать deskew, накопление, карту, tracking, TTC, изменять geometry/envelope, публиковать скорость в runtime или калибровать параметры.
- Source of truth: archive `dataset/for_hackathon/new_data`, его bag timestamps и PointCloud2; `README_dataset_audit.md`, `README_methodology.md`, `README_work_plan.md`.
- Этап: 5 — измерение/валидация дальности и движения.
- Вход: один `/lidar_points`, `hesai_lidar`, 11 271 облако. Временная база — только bag timestamps внутри этой записи; header/per-point timestamps не используются.
- Метод: origin-centric voxel sample статичной геометрии, trimmed point-to-point ICP между anchor-кадрами; длина — сумма норм относительных translation; скорость каждого интервала — `norm(translation) / Δbag_time`.
- Frames/transforms: оценивается относительное transform текущего source frame к предыдущему source frame; external frame не создаётся, `T_world<-lidar` и pose graph не заявляются.
- Allowed files: этот отчёт, узкий offline-скрипт в `scripts/`, JSON/CSV в `artefacts/stage_5/`, уточнение README после результата.
- Files to avoid: active detector/config, envelope, ROS2 schemas, bag, TF, calibration.
- Защищённые контракты: ICP не становится одометрией runtime; нельзя использовать результат для deskew/TTC/clear decision; низкий overlap/residual остаются видимыми.
- Основной агент: `lidar_obstacle_pipeline`; safety reviewer не нужен, так как production/safety-геометрия не меняется. Validation проход — по фактическим output и ограничениям claim.
- Validation target: L1 для полного офлайн-прогона и диагностического estimate; не выше L1 без независимой trajectory/одометрии.
- Validation method: полный проход по частей архива, exact message-count check, неперекрывающиеся anchors, сохранённые interval timestamps, transform norms, residual и correspondence fraction; sensitivity check по двум шагам anchor.
- Acceptance: репорт содержит estimate path/speed, coverage, residual/overlap и явный verdict о пригодности для точного метража.
- Stop conditions: нет метрического контракта/monotonic bag time, scan matching не сходится, либо для результата понадобятся protected runtime changes.

## Отчёт о завершении

- Что изменено: добавлены `scripts/estimate_new_data_lidar_motion.py`, полный JSON-артефакт `artefacts/stage_5/new_data_lidar_motion_2026-09-22.json` и отдельный раздел о движении `new_data` в `README_dataset_describtion.md`. Статичные сцены и движущаяся запись теперь разделены в документации.
- Evidence inspected: archive `new_data`, его `metadata.yaml`, 221 SQLite-часть, schema-aware `src/cloud_input.py`, существующий `scripts/analyze_new_data_motion.py`, аудит входа, методология и план работ.
- Commands run:
  - `docker run ... stage_2-player python3 scripts/estimate_new_data_lidar_motion.py --archive dataset/for_hackathon/new_data --output artefacts/stage_5/new_data_lidar_motion_2026-09-22.json --anchor-strides 10 50` — PASS.
  - PowerShell `ConvertFrom-Json` summary inspection — PASS: 11 271 сообщений metadata, 1 128 anchor-кадров, `hesai_lidar`, `/lidar_points`; 1 127/1 127 и 226/226 ICP-intervals respectively.
- Результаты: 10-frame anchors дают сумму норм relative ICP-translation 47,914 м и среднюю 0,0399 м/с (0,1438 км/ч); 50-frame anchors — 18,820 м и 0,0157 м/с (0,0565 км/ч). Median residual соответственно 0,174/0,188 м; median correspondence fraction 25,1/19,8%.
- Validation level achieved: L1 только для полного offline diagnostic run и его sensitivity check. Verdict: **PASS_WITH_RISKS** для утверждения «в `new_data` наблюдается движение и ICP можно исследовать»; **HOLD** для численного пути/скорости поезда.
- Что не проверено: внешний метрический контракт, IMU/odometry/TF, ground-truth trajectory, loop closure, absolute drift, оси/extrinsics, независимые путевые метки и relation header/per-point clocks.
- Известные FP/FN или safety-риски: ICP может принять изменение видимости/геометрию тоннеля за движение и недо- либо переоценить пройденный путь на кривой. Расхождение 2,5 раза между anchor steps прямо показывает нестабильность. Результат не используется для deskew, накопления, TTC, envelope или решения `CLEAR`.
- Следующий минимальный тест: получить хотя бы две контрольные отметки пути или поток одометрии/IMU с временным контрактом; сравнить LiDAR-trajectory с ними по whole-run error и drift. До этого сообщать только diagnostic relative motion.
- Residual risk: даже 100% число сошедшихся интервалов не доказывает корректность зарегистрированной траектории; correspondence fraction и residual не заменяют внешнюю валидацию.
