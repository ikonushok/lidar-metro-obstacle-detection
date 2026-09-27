# Прямой плеер: проверка разделения входов

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Актуальный контракт двух входов / датированный интеграционный результат. Scope проверки указан ниже; это не гарантия полного качества или скорости.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Дата: 2026-09-23. Этапы 5–6. Цель: вернуть плееру прямой C++-путь, сохранить ROS2-вход для сдачи и описать оба режима в корневом README.

## Изменение

`serve_stage_2_cpu_catalog.py` снова выбирает DirectDetailedCpuRuntime для development_candidate. Runtime запускает установленный `curve_pipeline_stream_cli` непосредственно по пути, найденному через ament index: без `ros2 run`, rclpy.init и DDS. Один запрос — одна запись XYZ в stdin и один JSON из stdout. Manifest/ответ содержат `runtime_transport=direct_cpp`.

Launcher различает direct_cpp/ros2 в имени контейнера и сообщении запуска. Явный исторический baseline сохраняет ROS2. ROS2-node с model_v1, core, модель, tangent, геометрия и пороги не менялись в этой задаче. Опция `-Measure` осталась отдельным ROS2-замером и обозначена так в README. Валидатор проверяет ROS2 parity отдельно, а HTTP-плеер — как direct_cpp. Артефакты новой проверки сохраняются отдельно от прежней интеграции.

В README обновлены архитектура, команды запуска/остановки, проверка и разграничение требований §3.3/4/8.6 ТЗ. ROS-библиотеки для чтения bag остаются зависимостями образа, даже когда плеер не запускает ROS2-узлы.

## Evidence и команды

Изучены HEAD af9151c и текущие runtime/server/launcher/validator, README, CMake install targets, существующие тесты CPU/catalog/JS и validation_reviewer. Данные: сохранённые XYZF doubleT_obstacle, исходный 26-byte PointCloud2 из extracted bag, архив для HTTP-каталога. Артефакты: `artefacts/stage_5/direct_player/`.

Выполнено:

```powershell
.\scripts\run_stage_2_cpu_player.ps1 -Port 8110 -RailForwardMinM 2 -ForwardExtensionMethod tangent -NoiseFilterMode model_v1 -NoBrowser -RebuildImage
.\scripts\validate_ros_model_pipeline.ps1 -Port 8110
node --test tests/test_cpu_viewer_distance_and_noise.cjs tests/test_cpu_viewer_envelope_geometry.cjs
git -c safe.directory=C:/Users/Ilya/PycharmProjects/lidar_MosMetro3D diff --check
```

В Docker с readonly mount `/workspace`, cwd `/workspace`, `PYTHONPATH=/workspace/scripts:/workspace/src` выполнены `python3 -m unittest discover -s tests -p "test_*cpu*py" -v` и отдельно `-p test_stage_4_all_sources_contract.py`.

- Сборка Humble/colcon: PASS, 1 пакет. Image manifest list `sha256:b4f387ac5ab667eb4f1b8fc205f9c569d5af8a894f207fdd0c03380040d5dce6`; `build_launch.log`.
- Python CPU/launcher: 11 PASS; каталог: 7 PASS; JS: 14 PASS.
- Сравнение 33 полей ROS2/direct на кадрах 0/13/64/145/185, UNKNOWN-проверки и исходное облако на 921600 точек через SHM: PASS; `parity.json`, `validation.log`.
- HTTP: кадр 13 — true/121 reportable points; кадр 145 — false/0; direct_cpp/model_v1, исходные stamp/frame совпадают; `viewer_http.json`.
- `docker top … -eo pid,ppid,args`: только Python HTTP server и `/app/install/lib/lidar_mosmetro3d_cpp/curve_pipeline_stream_cli 2.0 --use-model-filter`; ROS2-процессов нет, `processes.txt`.
- Дополнительные последовательные HTTP-запросы кадров 14/15/16 после загрузки SQLite: 299.0/205.6/206.7 мс; C++ roundtrip 113.6/131.1/122.2 мс (`warm_http_timings.json`). Это три отдельных кадра, не p95 и не сравнительный benchmark. HTTP включает чтение, обработку и передачу JSON, но не загрузку XYZF и отрисовку браузера. Известная проблема внутреннего processing_ms direct CLI здесь не исправлялась; эти значения получены независимыми wall-clock таймерами.

После проверки остановлен только старый ROS2-плеер на 8100, запущен direct_cpp-плеер той же командой без RebuildImage. Manifest на 8100 подтвердил direct_cpp/model_v1/tangent. Временный контейнер 8110 остановлен.

## Валидация и ограничения

Отдельный validation-проход текущего агента: PASS для указанного scope, L1 для тестов и L3 для фактической цепочки архив → direct C++ → HTTP-плеер. Это не независимый review и не проверка качества модели на новых данных.

Не проверены: ручная WebGL-отрисовка, длительная перемотка, весь набор данных, стенд организатора, p95/drop-rate. Повторная отправка и DDS исключены из основного пути архитектурно; абсолютное отсутствие любых задержек не заявляется. Первое извлечение SQLite и загрузка облака остаются затратными. ROS2 retry-loop отдельного адаптера не исправлялся.

Следующий минимальный тест: обновить страницу 8100 и проверить привычную перемотку после загрузки датасета. При остаточной задержке измерять чтение/HTTP/отрисовку отдельно, сохраняя прямой C++-путь.

## Дополнение: команды README без плеера

2026-09-23, запрос пользователя: добавить пошаговый запуск заказчиком. Изменён только README: сборка образа, отдельный контейнер с curve_envelope_node, `docker exec … /ros_entrypoint.sh ros2 topic echo`, `ros2 bag info/play`, остановка; указаны topic/frame конкретного bag и перенос команд в Bash.

На том же собранном образе реально выполнены команды README с именем проверочного контейнера `lidar-detector-readme-check` вместо `lidar-detector`. Источник — readonly mount `dataset/extracted/doubleT_obstacle` в `/data`, ROS_DOMAIN_ID=172, ROS_LOCALHOST_ONLY=1. `ros2 bag info /data`: 201 сообщений PointCloud2, 4.5 GiB, 20.392 секунды.

Первый запуск с SHM=512m дал ошибку создания сегмента при одновременной работе детектора, echo, daemon и player. В окончательном примере SHM=1g. Запуск без ограничения read-ahead не дал сообщения за 50 секунд ожидания; это не классифицировано как ошибка алгоритма. Добавлено `--read-ahead-queue-size 2`, чтобы ограничить память чтения.

С `ros2 bag play /data --rate 1.0 --read-ahead-queue-size 2` получен и разобран JSON через `ros2 topic echo /stage_3/curve_envelope_candidate std_msgs/msg/String --field data --once`: `runtime_transport=ros2`, `noise_filter_mode=model_v1`, `source_frame=lidar_livox`, `header_timestamp_ns=946687297199933052`, `status=NO_REPORTABLE_INTRUSION_NOISE_IGNORED`, candidate=false, safety=false. Для проверки echo дополнительно ограничен `timeout 100`. `ros2 topic info` подтвердил 1 publisher/1 subscription входного PointCloud2 и publisher результата. Проверочный контейнер остановлен; плеер 8100 не затронут.

Уровень L1 для конкретных CLI-команд и L3 для одного результата bag → node → echo без плеера. Полнота обработки всех 201 сообщений и real-time не проверялись: player сообщал `Message queue starved` на Windows bind mount, что явно отмечено в README. Следующий минимальный тест для сдачи — непрерывный replay на Ubuntu-стенде с подсчётом выходов и измерением задержек.
