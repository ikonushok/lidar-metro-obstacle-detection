# Перенос baseline на new_data — результат

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Дата: 2026-09-20. Этап 3. Цель: проверить перенос существующей покадровой обработки на короткую выборку новой записи с изменяющейся сценой. Спецификация: [план](stage_3_new_data_transfer_plan.md).

**Вывод: offline-перенос выполнен; обнаружение реальных препятствий и работа в реальном времени не доказаны.** Автопоиск рельсов дал гипотезу на 100 из 101 кадра. На одном кадре геометрия недоступна и результат остаётся UNKNOWN. Python-baseline сохранил кандидатов на всех 101 кадре, включая элементы инфраструктуры. Число кандидатов не является метрикой качества.

## Выборка и evidence

- Исследованы raw-проекции кадров 0, 5500, 10000, затем 1050, 1100, 1150; код input reader, baseline, AutoRails, live-envelope, геометрический контракт и ближайшие тесты.
- Использован результат уже запущенного отдельного анализа движения: `artefacts/stage_2/new_data_motion_full/summary.json`, `frames.csv`, `registration_1s.csv`. В нём прочитаны 11271 облако из 221 части. Повторный полный анализ в этой задаче не запускался.
- Несмотря на имя `registration_1s.csv` и JSON-ключ `one_second_registration`, актуальный шаг полного анализа — 50 кадров, около 5 с; использованы реальные interval_seconds. Эти данные не являются одометрией.
- Для эксперимента выбран интервал **1050–1150**, bag +104.999997611…114.996947503 с (9.996949892 с), до расчёта baseline на нём. Это development-выборка, не независимый test.
- В обоих соседних пятисекундных интервалах диагностическое ICP показывает изменение сцены, но residual около 0.29/0.32 м и доля соответствий в 10 см около 6.5/6.6%. Оценку не использовали для скорости, совмещения кадров или deskew.
- По исходным проекциям меняются видимая форма тоннеля и направление локальной оси. Это совместимо с движением датчика; точная траектория/скорость поезда не установлены.
- 101 исходное PointCloud2 из `new_data_20.db3`, `new_data_21.db3`, `new_data_22.db3`; `/lidar_points`, `hesai_lidar`, по 307200 исходных точек. Ненулевых конечных возвратов 173314–190326, nonfinite XYZ 0 в этой выборке. Архив не изменён.

## Изменения

- `config/geometry_new_data_experiment.yaml`: отдельная гипотеза в исходном `hesai_lidar`. Направление identity: **hesai_lidar ← hesai_lidar**; XYZ и header.frame_id не переименовываются. Это не extrinsics поезда.
- Высота прямой reference-линии Z=−1.1 взята как округлённая development-гипотеза по AutoRails на трёх контрольных кадрах. На ближнем сечении Y=−4 найденная средняя высота рельсов около −1.10. Оси −Y/X/Z и метры остаются ASSUMED, не внешней калибровкой.
- Размеры габарита, margin, clustering и остальные пороги сохранены из первого baseline. Существующие auto-grade/auto-track оценивают опору покадрово. Их объединение с прямым габаритом сохранено; оно может захватывать инфраструктуру на кривой.
- `src/stage_3_baseline.py`: добавлен явно выбираемый SOURCE_FRAME_IDENTITY_EXPERIMENT; чужой frame, неidentity transform и неподдержанные оси отвергаются. Старый профиль остаётся отдельным и не активирует hesai_lidar.
- `scripts/experiment_new_data_baseline.py`: ограниченное чтение исходных сообщений TAR/SQLite, JSONL, latency, hash исходного буфера, полные usable XYZ и проекции. При повторном использовании завершённого output отказ вместо перезаписи. Окончательная версия сохраняет исходный YAML-профиль и строковый header timestamp.
- `scripts/replay_new_data_visual.cjs`: отдельный прогон неизменённых AutoRails + live-envelope на экспортированных XYZ. Размеры reference берутся из прежнего player manifest, конфиги — из существующих web JSON. Параметры записаны в результат; эта команда требует существующий export первого датасета.
- `scripts/render_new_data_transfer.py`: иллюстрация по сохранённым данным. Плеер и комментарий о перекрывающих обзор расстояниях не изменялись. Экспериментальный профиль не включён в общий просмотр всей new_data.

## Результаты двух веток

Это разные существующие ветки; их числа нельзя считать сравнением одинаковых режимов.

| Показатель | Python baseline | AutoRails + live-envelope / Node |
|---|---:|---:|
| Обработано кадров | 101/101 | 101/101 |
| Кадры с геометрическими кандидатами | 101 | 100 |
| Нет текущей оси | отдельная auto-grade/track + прямой fallback | 1: frame 1054 |
| Изменённые исходные буферы | 0 | 0 |
| Медиана расчёта, мс | 204.05 | 44.87 |
| p95, мс | 248.66 | 59.41 |
| Максимум, мс | 289.47 | 94.82 |

Python: 58–137 кластеров и 25–77 дополнительных above-floor компонентов на кадр. Проекции показывают захват нижней поверхности, стен/свода и протяжённых участков; считать это реальными помехами нельзя. Профиль 200 м не доказывает обнаружение на этой дальности. Python-время превышает ориентир 100 мс/кадр.

Node: поиск оси не менялся. Поддержанная ближняя граница 4–10 м, дальняя 20–38 м. На кадрах 1050/1100/1150 интервалы 4–34 / 4–28 / 4–22 м. За пределами участка возвраты UNKNOWN. Frame 1054: `NO_STRAIGHT_CONSISTENT_PAIR` → `MISSING_CURRENT_ENVELOPE`, все 189984 usable возврата UNKNOWN, расстояние отсутствует. Сохранённый системный статус всех кадров UNKNOWN.

Профиль Node строится вдоль текущей пары рельсов и не продолжает её до 200 м; core — reference [-1.4,1.4] × [0,3.7], внешние отступы по 0.5 м. У Python core дополнительно расширен margin 0.2 м, warning bottom 1.3 м; маски объединяют несколько гипотез. Поэтому число кандидатов и времена этих веток не являются абляцией.

Время Python включает evaluate_cloud (с input inspection), исключает TAR/SQLite I/O, экспорт и рендер; Node включает AutoRails + геометрию + checker, исключает файловый I/O и UI. Node v24.19.0 / Windows, Intel Core Ultra 7 265K, 20 логических CPU; Python в Docker: Ubuntu 22.04.5 / ROS2 Humble / Python 3.10.12. Не стенд из ТЗ; очередь, dropped frames, ROS2 end-to-end и real-time не проверялись. Наносекунды header берутся строкой из результата Python, а не из округлённого JS Number.

## Выполненные команды и проверки

Контейнерные команды использовали существующий `lidar-mosmetro3d:stage_2-player`, bind проекта в `/workspace:ro`, `artefacts` в `/output:rw`, `PYTHONPATH=/workspace/src`. Новые зависимости не устанавливались.

```text
python3 /workspace/scripts/experiment_new_data_baseline.py --archive /workspace/dataset/for_hackathon/new_data --output /output/stage_3/new_data_transfer/probe --indices 0 5500 10000
python3 /workspace/scripts/experiment_new_data_baseline.py --archive /workspace/dataset/for_hackathon/new_data --output /output/stage_3/new_data_transfer/window_inspection --indices 1050 1100 1150
python3 /workspace/scripts/experiment_new_data_baseline.py --archive /workspace/dataset/for_hackathon/new_data --output /output/stage_3/new_data_transfer/baseline_1050_1150 --start 1050 --count 101 --config /workspace/config/geometry_new_data_experiment.yaml --export-xyz
node scripts/replay_new_data_visual.cjs
python3 /workspace/scripts/render_new_data_transfer.py /output/stage_3/new_data_transfer/baseline_1050_1150
```

Все пять команд завершились exit 0. Выходную директорию повторного эксперимента следует задавать новую. SHA256 профиля: `40c6e047542e5dfa894cbd08ecbf257f8c3160b3b4c7b367946ab36fdf0e9373`.

Тесты через `docker exec --env PYTHONPATH=/workspace/src:/workspace/tests lidar-player-catalog-8081 python3 -m unittest discover -s /workspace/tests -p <имя> -v`:

- `test_new_data_profile.py`: 5 PASS; низкая точка, граница, чужой frame, неверное преобразование/оси, запрет safety/CLEAR.
- `test_stage_3_baseline.py`: 11 PASS.
- `test_protrusion_segmentation.py`: 3 PASS; низкие препятствия не подавляются.
- `test_geometry_contract.py`: 4 PASS; старый контракт сохранён.
- `node --test tests/test_auto_rails.cjs tests/test_live_envelope.cjs`: **12 PASS, 1 FAIL**. UI lifecycle-тест ожидает текст «Автоось» в `auto-status`, тогда как текущий `web/stage_2_review_layers.js` при найденной оси присваивает пустую строку. Чтение по bug-reproducer ограничено этим несоответствием; тест/плеер не менялись. Полный набор проверок не зелёный; дефект вычисления оси этим падением не доказан.

При добавлении снимка профиля однокадровый smoke сначала завершился TypeError: YAML-дата не сериализуется в JSON. Экспортёр сохраняет исходные байты YAML вместо JSON-сериализации. Повтор точной команды на frame 1054/count 1 в `final_runner_smoke` — exit 0. Дополнительный `node scripts/replay_new_data_visual.cjs artefacts/stage_3/new_data_transfer/final_runner_smoke` — exit 0, повторно подтверждён UNKNOWN без текущей оси. Эта окончательная правка касается metadata экспорта; вычислительный baseline 101 кадров не менялся. Проверена совпадающая строковая идентичность header.

Попытки рендера локальным `python`/bundled Python не удались (нет команды / нет matplotlib), соседняя venv недоступна из sandbox. Рендер выполнен установленным matplotlib в существующем Docker-образе; пакеты не устанавливались.

## Safety-review и validation

Отдельные последовательные проходы текущего агента, не независимое review. Safety verdict: **PASS_WITH_RISKS для offline development**. Нет deskew, накопления, обновления фона или удаления пола/рельсов. Все XYZ сохранены; неверный контракт блокирует профиль, отсутствующая текущая ось даёт UNKNOWN. Чистый путь не заявляется; реальные низкие препятствия в этой записи не размечены.

Validation: **L1** только для указанного offline-интервала и узких проверок. Глобального PASS нет из-за описанного UI-теста. ROS2 publisher/subscriber для нового профиля не проверен. Разметки инфраструктуры/помех и независимого проезда нет; recall, precision, FP/мин, пропуски объектов и точность расстояния не рассчитаны.

Остаточный риск: прямые/линейные гипотезы на кривой, непроверенные mounting/units/clearance, искажения скана и попадание штатной геометрии в кандидаты. Следующий минимальный тест: разметить короткий чистый интервал и видимое препятствие на new_data, проверить попадания/пропуски в поддержанном участке. Затем решать, требуется ли кривая ось/deskew; не подавлять инфраструктуру до теста низкого препятствия.

## Артефакты

- Python summary: `../../../artefacts/stage_3/new_data_transfer/baseline_1050_1150/summary.json` — локальный артефакт недоступен; [восстановление](../../README_history.md#восстановление-недоступных-артефактов)
- Покадровые исходные метаданные и Python-кандидаты: `../../../artefacts/stage_3/new_data_transfer/baseline_1050_1150/frames.jsonl` — локальный артефакт недоступен; [восстановление](../../README_history.md#восстановление-недоступных-артефактов)
- AutoRails + live-envelope: сводка и все кадры: `../../../artefacts/stage_3/new_data_transfer/baseline_1050_1150/visual_replay.json` — локальный артефакт недоступен; [восстановление](../../README_history.md#восстановление-недоступных-артефактов)
- Иллюстрация: `../../../artefacts/stage_3/new_data_transfer/baseline_1050_1150/transfer_overview.png` — локальный артефакт недоступен; [восстановление](../../README_history.md#восстановление-недоступных-артефактов)

Пути выше относительно этого отчёта ведут через корень репозитория.
