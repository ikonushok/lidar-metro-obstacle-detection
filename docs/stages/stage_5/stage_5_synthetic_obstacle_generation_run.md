# Генерация синтетических препятствий — отчёт выполнения

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Эксперимент/справка вне запуска direct_cpp+tangent+model_v1. Включение требует отдельной проверки эффекта и регрессии; результаты не меняют runtime default.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

## Результат

Реализован development-only ROS 2 генератор, который вставляет `box`, произвольно ориентированные `cylinder` и `ellipsoid` в реальный `PointCloud2`. Примитивы объединяются в один составной object-level ground truth. Для каждого ненулевого конечного исходного возврата используется фактическое направление луча. Исходная точка заменяется только если ближайшее синтетическое пересечение находится перед ней; тем самым моделируется first-return окклюзия без создания вымышленного регулярного scan pattern.

Генератор сохраняет header, frame, размеры, offsets, endianness, `point_step`, `row_step`, padding, порядок точек, `ring` и per-point `timestamp`. Публикуются дополненное облако и JSON ground truth. При несовпадении `frame_id` с контрактом публикуется только `SYNTHETIC_GENERATION_ERROR`, дополненное облако не публикуется.

## Использование

Проверка конфигурации:

```bash
python3 -m synthetic_obstacle_generator \
  --config /app/config/synthetic_obstacles_development.yaml \
  --validate-config
```

Запуск в ROS 2 Humble:

```bash
python3 -m synthetic_obstacle_generator \
  --config /app/config/synthetic_obstacles_development.yaml \
  --scenario-id dog_standing \
  --input-topic /sensing/lidar/hesai128/pointcloud \
  --output-topic /synthetic/pointcloud \
  --ground-truth-topic /synthetic/ground_truth
```

Без `--scenario-id` каталог циклически переключается каждые 20 кадров. Доступны 12 сценариев: `standing_person`, `lying_person`, `dog_standing`, `dog_lying`, `suitcase`, `low_box`, `crowbar`, `shovel`, `jacket_bundle`, `pipe_across_track`, `cable`, `maintenance_trolley`. Координаты находятся непосредственно в `lidar_livox`; выполняется только явно заданный identity-контракт `lidar_livox <- lidar_livox`.

## Что изменено

- `src/synthetic_obstacle_generator.py`: валидация контракта, ray casting трёх примитивов, составные объекты, fixed/cycle selection, first-return окклюзия, детерминированный dropout, изменение копии `PointCloud2`, ground truth и ROS 2 wrapper.
- `config/synthetic_obstacles_development.yaml`: 12 отдельных сценариев, 12 object-level объектов и 40 геометрических частей.
- `tests/test_synthetic_obstacle_generator.py`: узкие геометрические, schema и failure-path тесты.
- `docs/stages/stage_5/stage_5_synthetic_obstacle_generation.md`: task spec.
- `docs/README_synthetic_obstacles.md`: центральный план матрицы placements, manifest/point labels, split, первоначальной статистики, переобучения `model_v2`, проверки до/после и возможного перехода к Blender mesh.

Детектор, geometry contract, C++ pipeline, пороги и исходные bag не изменялись.

## Evidence inspected

- `agents/context_router.md`, `agents/lidar_obstacle_pipeline.md`;
- `agents/safety_geometry_reviewer.md`, `agents/validation_reviewer.md`;
- `docs/README_methodology.md` §17, `docs/README_dataset_audit.md`;
- `src/cloud_input.py`, `src/stage_3_baseline.py`, соседние unit-тесты;
- `Dockerfile` и фактическая схема исследованных `PointCloud2`.

## Выполненные команды и результаты

1. Узкие тесты генератора в существующем образе: первоначально 1 тест выявил неверное ожидание для луча, фактически пересекающего бок цилиндра; тест разделён на независимые side/cap случаи. После исправления: `8/8 OK`.
2. Связанные тесты `cloud_input`, `stage_3_baseline`, генератора: `25/25 OK`.
3. CLI config validation первой версии: `{"obstacles": 2, "status": "SYNTHETIC_DEVELOPMENT_ONLY"}`.
4. ROS wrapper import в Humble-образе: `SyntheticObstacleNode`.
5. `docker build --progress plain -t lidar-mosmetro3d:synthetic-obstacles .`: успешно; C++ ROS-пакет собран, `1 package finished`.
6. После safety-прохода добавлены oriented-box и zero/NaN проверки.
7. Первая версия образа: итоговый связанный запуск непосредственно из образа `27/27 OK`.
8. Дополнение 2026-09-23: добавлены arbitrary-axis cylinder, ellipsoid, составные объекты, explicit/cycle scenario selection и 12 сценариев первой выборки.
9. Финальная CLI-проверка из пересобранного образа: `{"objects": 12, "parts": 40, "scenarios": 12, "status": "SYNTHETIC_DEVELOPMENT_ONLY"}`.
10. Финальный связанный запуск из пересобранного образа: `30/30 OK`; каждый сценарий отдельно проверен контрольными лучами через центры его частей.
11. Документационная проверка `docs/README_synthetic_obstacles.md`: `git diff --check` без ошибок; `LOCAL_LINKS_OK count=5`. Runtime после документационной правки не перезапускался.

Локальная `.venv` не использована: её launcher ссылается на отсутствующий `C:\Users\Ilya\AppData\Local\Programs\Python\Python312\python.exe`. Проверка выполнена в Ubuntu/ROS 2 Humble Docker.

## Safety review

- Verdict: `PASS_WITH_RISKS` текущим агентом; независимое review не заявляется.
- Frame и transform однозначны: только `source <- source`; mismatch прекращает генерацию облака.
- Header и per-point timestamps не пересчитываются и не смешиваются; deskew не заявлен.
- Нулевые и non-finite возвраты не становятся лучами; низкий box не удаляется.
- Сценарий выбирается явно либо детерминированным циклом; его id записывается в ground truth.
- Границы 20-кадровых блоков являются границами разных synthetic events; их нельзя оценивать как один непрерывный объект или использовать для настройки temporal-порогов без отдельного протокола.
- Генератор не выдаёт `CLEAR`, risk, confidence или safety decision.
- Исходное сообщение не изменяется; модифицируется глубокая копия.

## Validation review

- Claim: код процедурной вставки и ROS 2 wrapper реализованы, конфигурация валидируется, узкие и связанные тесты проходят в Humble Docker.
- Verdict: `PASS_WITH_RISKS`.
- Validation level achieved: **L1** — выполнены узкие реалистичные unit/schema проверки и свежая Docker-сборка. Целевой L2 из task spec не заявлен: не выполнен replay настоящего bag и визуальная проверка результата.
- Synthetic данные не являются evidence real-world recall/precision и не создают независимый positive test.

## Непроверенное и residual risk

- Настоящий `doubleT_obstacle`/чистый Livox-интервал через узел не replay-ился.
- QoS и запись нового rosbag с обоими выходными топиками не проверены end-to-end.
- Интенсивность по умолчанию константная и физически не откалибрована.
- Используются только направления лучей с существующим ненулевым возвратом; лучи без возврата не восстанавливаются.
- Не моделируются divergence, multi-return, material response, шум дальности, deskew и движение объекта внутри скана.
- Координаты примера используют `ASSUMED_HACKATHON` оси/метры, а не подтверждённую калибровку.
- Размеры, позы и дистанции 12 объектов заданы вручную как development proxies; это не статистическое распределение реальных препятствий.
- Производительность на кадре 921 600 записей пока не измерена.

## Следующий минимальный тест

Replay одного вручную выбранного чистого интервала `lidar_livox`, запись `/synthetic/pointcloud` и `/synthetic/ground_truth`, визуальная проверка минимум низкого, тонкого и составного сценариев и прогон неизменённого детектора на исходном и синтетическом облаке. После этого отдельно измерить p95 и память на полном размере кадра.
