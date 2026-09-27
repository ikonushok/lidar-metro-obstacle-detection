# Разделение выступов над полом

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

Цель: выделить дополнительную локальную компоненту у человека OBS-003,
чья anchor-точка входила в компоненту длиной 38 м. Проверка development:
кадры 55 и 160 и синтетический сценарий пола, выступа и низкого препятствия.
Метод: дополнительная связность точек выше локального пола в калибруемой
полосе высот. Исходные компоненты и статусы не изменяются, низкие точки
не исключаются из основного детектора. Новые компоненты не являются
семантическим детектором людей. TF, единицы, профиль и ROI не меняются.
Параметры в geometry_contract; целевой уровень L1. Safety review текущим
агентом: проверить отсутствие подавления baseline и UNKNOWN при нет пола.
Validation: сравнить обе пользовательские точки с новыми компонентами,
затем обновить результаты и manifest для просмотра. Не заявлять recall
по одной точке, не считать число компонентов метрикой качества.

## Результат — 2026-09-18

Добавлена дополнительная above-floor сегментация в stage_3_baseline.py,
параметры в config/geometry_contract.yaml. Loader сохраняет protrusion_clusters;
плеер показывает их отдельным розовым слоем. Исходные clusters и статусы
не заменяются. Подготовлены дополнительные компоненты для всех 201 кадров.

Изучены пользовательские anchors из config/person_annotations_development.json,
сырые xyzf, manifest и stage_3_results.jsonl. В кадре 55 anchor OBS-002
попадает в bounds компоненты из 119 точек, в кадре 160 anchor OBS-003 —
в bounds компоненты из 1641 точки размером примерно 0.57 × 0.68 × 1.31 м.
Evidence: artefacts/stage_3/metrics/person_anchor_check.json. Попадание точки
в bounds не доказывает точную сегментацию всего человека.

Выполнено в Docker lidar-mosmetro3d:stage_3_baseline с текущим репозиторием
в /workspace и PYTHONPATH=/workspace/src:

- python3 -m unittest discover -s tests -v — 40/40 PASS;
- python3 -m unittest discover -s tests -p test_stage_2_player_results.py -v —
  2/2 PASS после добавления проверки переноса нового поля;
- python3 scripts/check_person_anchors.py — обе source-точки проверены;
- python3 scripts/prepare_protrusion_overlay.py — обновлены 201 кадров;
- python3 scripts/prepare_stage_2_player.py /data --output
  /workspace/artefacts/stage_2/player_doubleT_obstacle --stage-3-results
  /workspace/artefacts/stage_3/stage_3_results.jsonl --web-source
  /workspace/web/stage_2_player.html --attach-stage-3-to-existing-manifest —
  201 кадров, attached=true.

Browser-проверка localhost:8080: кадр 160, новый слой включён, baseline и оба
габарита выключены; розовые рамки отображаются независимо. Полная визуальная
оценка всех кадров не выполнена.

Safety-review текущим агентом: исходные кандидаты не подавляются, низкое
препятствие сохраняется (регрессионный тест); без оценки пола новый слой пуст,
это не CLEAR и не замена основного результата. Validation-проход тем же
агентом: L1 в области перечисленных тестов и development anchors, не
независимая проверка. Параметры остаются ASSUMED_HACKATHON.

Ограничения: точность пола, семантическая классификация, recall/FP и границы
людей не валидированы. Исходный processing_ms сохранён как время старого
baseline; offline supplement имеет отдельное время и scope, суммарную
производительность обновлённого ROS-конвейера не измеряли. Следующий
минимальный тест — просмотр рамок около обоих anchors и соседних кадров
с ручной оценкой полноты человека и примеси пола.
