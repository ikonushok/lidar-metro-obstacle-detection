# Единая геометрия покадрового габарита и проверки пересечений

<!-- documentation-status D0-D3 2026-09-23 -->
> **Статус документа:** Историческая спецификация/результат этапа. Режим, дата и scope — зафиксированные ниже; старые команды и ближайшие шаги не являются текущей инструкцией.
> [Актуальный запуск](../../../README.md) · [Текущий план](../../README_work_plan.md) · [Результат D0–D3](../stage_5/stage_5_documentation_d0_d3.md). Исторические числа не пересчитаны; если commit проверки не указан ниже, он здесь не восстанавливается предположением.
<!-- /documentation-status -->

## Задача — 2026-09-20

- Режим patch/validation. Пользователь одобрил объединение видимого габарита с проверкой попадания и проверку по доступной ручной разметке.
- Цель: новый live-расчёт пересечений raw XYZ с текущей auto/manual геометрией плеера; одна ось, профиль, отступы и продольный интервал для отображения/crop/классификации. Выделение геометрических кандидатов, расстояние до ближайшей исходной точки, диагностика и экспорт evidence.
- Этап 3 (envelope-only candidate baseline), интеграция Stage 2 viewer. Источники: запрос, docs/README_methodology.md §5–6 и правила evaluator, docs/README_dataset_audit.md, существующий reference profile manifest и config/geometry_contract.yaml. Требование ТЗ «наличие препятствия и ближайшее расстояние» здесь покрывается только кандидатом по assumed geometry, не готовым safety detector.
- Вход: неизменённый export doubleT_obstacle, сначала 0/55/100/160/200; existing user anchors config/person_annotations_development.json. Новая независимая разметка отсутствует. Оба anchors вне поддержанного интервала автооси (55: [4,44], anchor ~56.34; 160: [4,36], anchor ~3.42 по -Y).
- Source XYZ остаются рабочими; cloud transform identity. Локальная параметризация current_axis <- source только для вычисления пересечения, не перемещения облака. Оси и метры ASSUMED; время bag для replay, header/frame для идентичности; вычисления performance.now().
- Non-goals: смена размеров профиля/отступов, параметры AutoRails, удаление пола/рельсов, background, карта, TF/deskew, новая ML-модель, ROS2 interfaces, переписывание сохранённых Stage 3 результатов, CLEAR и эксплуатационная готовность.
- Allowed: web/stage_2_review_layers.js (единые geometry helpers/integration), web/stage_2_raw_player.html, новый web/stage_3_live_envelope.js и его config, scripts/run_stage_2_player.ps1, tests live/check/replay, этот отчёт, новые artefacts/stage_3/live_envelope и served assets. Исходные datasets/manifest/annotations/geometry_contract/старые results не менять.
- Grouping: baseline-compatible .25 м, 26 соседей, минимум 5 для рамки; параметры явные в новом config. Все внутригабаритные точки учитываются независимо от размера группы. Малые/низкие кандидаты не подавляются; рамка — группировка, не доказательство объекта. Для membership используем существующий numeric tolerance 1e-6.
- Решение: CORE/MARGIN/OUTSIDE_REFERENCE только внутри поддержанного интервала, UNKNOWN вне него/при отсутствующей геометрии. System/safety status остаётся UNKNOWN даже без пересечений. Кандидат появляется немедленно при любой CORE/MARGIN точке, без временной фильтрации.
- Смена кадра/оси/профиля/margins сбрасывает или пересчитывает live evidence. Crop и прочие визуальные слои не влияют на detector input; старый Stage 3 явно назван архивом. Расстояние — евклидово от source origin до ближайшего реального возврата, не до центра рамки; дополнительно s от начала поддержанного сегмента с явной подписью.
- Acceptance: геометрия рамок и membership одна; сдвиг/yaw/grade/margins меняют оба согласованно; точки на всех границах и низкие точки остаются кандидатами; конец сегмента не превращается в outside/clear; bad config/axis/NaN не дают ложный результат; source bytes и frame identity сохранены.
- Validation: Node unit/integration + development replay + строгая проверка frame/header/source для пользовательских anchors; браузер 0/55/160/200, смена геометрии/margins, raw-only/crop; PowerShell parser и launcher. Target L1 + browser integration, без precision/recall claims.
- Основная роль lidar_obstacle_pipeline. Затем отдельные safety-review и validation текущим агентом (не независимые). Проектная среда Ubuntu22.04/Humble/Docker, фактическая проверка Node/Windows и действующий Docker HTTP.
- Stop: не экстраполировать ось ради позитивного результата anchors; не выдавать selected detector candidate за independent ground truth. Для подтверждения качества нужен размеченный объект в поддержанном интервале и независимый проезд.

## Выполнение

Реализована новая live-ветка в плеере, не миграция ROS2/backend Stage 3.
`ReviewGeometry.createEnvelope` создаёт проверенный immutable snapshot оси,
core, expanded bounds и tolerance. Renderer берёт rings из этого snapshot;
live checker использует его же через `classifyLocal`. Crop применяет те же
проверки границ/интервала. Поддельный/несогласованный geometry object не принимается.
Геометрия/конфигурация экспортируются вместе с identity кадра и результатом.

`web/stage_3_live_envelope.js` считает четыре класса на полном исходном
буфере: CORE, MARGIN, OUTSIDE_REFERENCE и UNKNOWN. Вне продольного интервала
нельзя получить outside/clear. При любом CORE/MARGIN возврате немедленно
выдаётся кандидат, даже без достаточных точек для рамки. Группы .25 м/26
соседей строятся отдельно для core и margin. Порог 5 относится только к
отображаемой рамке, не к факту пересечения и не к ближайшему расстоянию.
При лимите voxel группировка отключается с диагностикой, все точки/кандидаты
сохраняются. Фильтрации земли, рельсов, фона или по высоте нет.

Показаны красные core и жёлтые margin точки, опциональные рамки, счётчики,
ближайшие реальные source-возвраты и JSON export. Ручная отметка получает
геометрический класс точки (не всего объекта). Старые Stage 3/protrusion/audit
переименованы в архив, по умолчанию выключены и не влияют на live результат.
Изменение frame/axis/margins пересчитывает snapshot; визуальный crop/цвета
не меняют raw input. UNKNOWN и пустые результаты очищают старую геометрию,
расстояния и экспорт. Пустой результат при валидной гипотезе не равен CLEAR.

Launcher публикует новые assets и URL `http://localhost:8080/?v=live-envelope-1`.
Новый заголовок «Габарит и пересечения · текущий кадр». Bags, manifest,
annotations, AutoRails config, geometry_contract и старые Stage 3 results
не менялись. Новых зависимостей/образов не добавлено.

## Команды и результаты

- `node --test tests/test_live_envelope.cjs tests/test_auto_rails.cjs tests/test_review_layers.cjs tests/test_raw_player.cjs`
  — 23/23 PASS. Все грани/углы rotated/translated/graded габарита, margin,
  неизвестные концы сегмента, низкий singleton, ближайшая точка не центр рамки,
  разделённые зоны кластеризации, лимит группировки, invalid input/config/axis,
  immutability и прежние тесты AutoRails/raw/manual. Интеграционный тест
  проверяет реальный обработчик export через Blob: identity/counts/geometry
  совпадают с текущим расчётом, изменённый margin попадает в новый JSON.
- `node tests/replay_live_envelope.cjs` — кадры 0/55/100/160/200, PASS;
  `artefacts/stage_3/live_envelope/development_sample.json`.
- `node tests/replay_live_envelope.cjs --all` — 201 кадров, 0 изменённых
  source buffers, суммы классов совпадают с исходным числом точек; 0 отказов
  группировки. `artefacts/stage_3/live_envelope/development_full_replay.json`.
  Во всех кадрах есть core-пересечения, что не доказывает 201 помеху.
  Проверенный по оси интервал содержит 31.26–45.49% source-возвратов;
  это доля точек, не доля видимости тоннеля и не recall.
  Node/Windows, auto+membership+grouping без загрузки и WebGL:
  median 41.28 мс, p95 48.99 мс, max 97.12 мс. Не real-time claim на стенде.
- PowerShell `Parser.ParseFile scripts/run_stage_2_player.ps1` — ошибок нет.
- `.\scripts\run_stage_2_player.ps1 -NoBrowser` с разрешённым доступом к Docker
  — exit 0, действующий сервер 8080 переиспользован, rebuild/re-export не было.
- Браузер через computer-use: реально открыта новая страница, проверены
  0/55/160/200, red/yellow points, дополнительные рамки на кадре 200,
  правильные counts/identity и отсутствие старого слоя при смене кадра.
  На кадре 0 правый margin .5 -> 0 уменьшил margin points 15160 -> 12443,
  core остался 842. При включении crop отображались 206489/346808 точек,
  live по-прежнему считал полные исходные 346808 (не результат crop).
  Параметры проверки восстановлены, временная вкладка закрывается.
- Нажат экспорт из браузера; фактически прочитан
  `C:/Users/Ilya/Downloads/live_envelope_frame_0.json` (29287 bytes).
  Через Node/assert сверены format/frame/header/counts/nearest_core с
  development_full_replay.json, safety=false, system=UNKNOWN, mode=auto,
  отсутствие массивов labels, axis endpoints и expanded bounds. Проверка PASS.

Пример результата при исходных отступах .5 м:

| Кадр | Участок по -Y, м* | Core points | Margin points | UNKNOWN points | Ближайший core-возврат, м* |
|---|---|---:|---:|---:|---:|
| 0 | 4–36 | 842 | 15160 | 193204 | 4.436 |
| 55 | 4–44 | 830 | 15737 | 189820 | 4.428 |
| 160 | 4–36 | 853 | 15095 | 196490 | 4.380 |
| 200 | 4–44 | 830 | 15757 | 189748 | 4.432 |

Ближайшая core-точка кадра 0: x=-.967761, y=-4.051881, z=-1.524401,
высота над модельной осью .016806 м*. Геометрически это кандидат у уровня
рельса, не подтверждённая посторонняя помеха. Рамки групп инфраструктуры
могут быть длинными; не интерпретировать каждую группу как отдельный предмет.

## Проверка существующей пользовательской разметки

У обеих отметок проверены first header записи, frame index, header/source
кадра и фактическое присутствие source-точки (по два одинаковых возврата).
Класс точки сверён с массивом результатов нового checker.

| Отметка | Кадр | Координата -Y, м* | Поддержанный интервал | Результат |
|---|---:|---:|---|---|
| OBS-002 | 55 | 56.340 | 4–44 | UNKNOWN, дальше конца |
| OBS-003 | 160 | 3.416 | 4–36 | UNKNOWN, перед началом |

Не считались TP/TN, не рассчитывались precision/recall: это user-selected
development points, не независимая object-level разметка; обе точки вне
области применимости оси. Эти реальные помехи новая ветка пока не покрывает.
Синтетические low/boundary fixtures подтверждают логику, не полевое качество.

## Отдельный safety-review текущего агента

PASS_WITH_RISKS для геометрических кандидатов в viewer. Проверены общий
snapshot renderer/checker, одинаковая численная граница crop, source bytes,
frame identity, немедленный singleton, unknown область и сброс stale results.
Ни кластеризация, ни crop не подавляют core points. Нет CLEAR, TTC, риска как
вероятности или автоматического обучения фону. Review не независимый.

Остаточные риски: reference-прямоугольник включает штатные возвраты у рельсов;
не моделируются поперечный уклон, underframe/body profile и кривизна пути.
Часть core-кандидатов может быть инфраструктурой. Ось/метры/профиль остаются
ASSUMED, область близко к датчику и дальняя часть неизвестны. Фильтром высоты
эти проблемы не скрывались, поскольку он мог бы удалить низкую помеху.

## Последующий validation-проход тем же агентом

Уровень L1 + browser integration/201-frame computational regression одного
development export. Подтверждена связь геометрии и membership, а не способность
уверенно отличать помехи от штатной инфраструктуры. ROS2 backend не мигрирован;
новый live module отдельно импортируется Node replay и браузером, архивная
ветка не менялась. Полный тест разных проездов/инфраструктуры не выполнен.

Следующий минимальный тест: разметить физическую помеху и рельсы внутри
поддержанного сегмента, проверить ошибку оси и статус всего объекта. Отдельно
нужны подтверждённые геометрия ближнего участка/дальнего пути и профиль у
рельсов; до их согласования не расширять диапазон и не удалять низкие точки.
