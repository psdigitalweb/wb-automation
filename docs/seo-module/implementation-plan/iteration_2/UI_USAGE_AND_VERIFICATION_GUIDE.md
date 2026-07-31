# SEO Module UI Usage and Verification Guide

Руководство по использованию и проверке UI модуля SEO после Итераций 1 и 2. Документ написан для оператора / PM / CEO и намеренно ограничен тем, что уже реализовано. Ничего за рамки Iteration 1 / Iteration 2 не описывается.

---

## 1. Краткий обзор (executive overview)

**Что UI должен помочь решить сейчас.**
UI модуля SEO сейчас существует не для того, чтобы «публиковать карточки», а для того, чтобы оператор мог понять:

- готова ли категория к тому, чтобы ей вообще доверять (категория 812 — единственная, по которой проводится реальная проверка);
- насколько текущий алгоритм подбора запросов (matcher) согласуется с человеческой разметкой;
- чем отличается старый (current) путь подбора запросов и новый (candidate) путь;
- можно ли на основе подобранных запросов генерировать текст, и если да — то только как research preview, а не как публикуемый контент;
- где проходит граница между «оператор одобрил» и «eval подтвердил».

**Current vs candidate.**
Старая цепочка (current path) — это `run_query_selection` + `SeoSkuQuerySet(status='confirmed')`, она работает как раньше и ничего не потеряла. Новая цепочка (candidate path) — это `matcher_v2` → `SeoMatcherRun`/`SeoMatcherResult` → проекция в `SeoSkuQuerySet(status='candidate', approval_state=...)`. Эти две цепочки идут параллельно и не перетирают друг друга. В UI должна быть явно видна пометка «current» или «candidate».

**Preview vs production.**
Вся генерация в Iteration 2 — это research preview. Флаг `SEO_GENERATION_PREVIEW_ENABLED` по умолчанию выключен; даже когда его включают на dev/staging, на выходе получается `content_kind='preview'`, `mode_used='research_preview'`, `publishable=false`. Production-генерации (то есть контента, пригодного к публикации в WB) в Iteration 2 нет и быть не может.

**Approved vs validated.**
Это два разных типа доверия и их нельзя смешивать:

- **Approved** — оператор вручную подтвердил конкретный candidate query set (или нажал «accept» в human review формы). Это субъективное решение одного человека.
- **Validated** — eval-прогон на размеченном датасете сказал, что категория прошла пороги качества, и `eligibility_tier` переключился на `evaluated` или `approved`. Это объективный сигнал по метрикам.

Промоушн по gates требует обоих: без validated-тира кнопка «promote» физически не должна пропустить контент дальше preview.

**quality_mode.**
Это честная метка того, какого качества были входы у конкретной операции:

- `full` — все сигналы полноценные;
- `preview` — используется локальный preview-эмбеддер или иной бюджетный провайдер;
- `degraded` — один или несколько сигналов ослаблены (отсутствуют атомы, тонкий профиль, нет readiness и т. п.);
- `fallback` — произошёл аварийный откат, результату нельзя доверять как представителю алгоритма.

`quality_mode` проталкивается по цепочке: SKU-meaning → matcher_v2 → query set → generation. Его нельзя интерпретировать как «оценку» — это описание условий, в которых результат был получен.

**Category tier.**
`eligibility_tier` на `SeoCategoryMatchingReadiness` описывает, насколько категория в принципе пригодна для следующего шага пайплайна:

- `preview_only` — можно только смотреть, ничего не продвигать;
- `evaluated` — eval прогнан, метрики в допустимом диапазоне, допустим первый шаг промоушна (`preview → candidate`);
- `approved` — eval пройден по более строгому порогу, допустим второй шаг (`candidate → approved`); дальше (`approved → published`) всё равно отказ.

Tier пишется **только** eval-харнесом; UI и оператор менять его не могут.

---

## 2. Основные концепции и бейджи

### `QualityBadge`

Визуальный индикатор `quality_mode` рядом с SKU / query set / generation.

| Режим | Что значит | Что делает оператор | Блокирует ли что-то |
|---|---|---|---|
| `full` | Все сигналы полные, провайдер — production-класса, профиль и readiness на месте | Нормальный режим работы | Ничего не блокирует |
| `preview` | Использовался local preview embedding provider или промежуточный сигнал помечен preview | Можно смотреть и сравнивать, но не принимать как референс | Блокирует интерпретацию как «эталон качества» |
| `degraded` | Есть хотя бы одна причина деградации (см. `degraded_reasons`) | Открыть tooltip/подсказку, посмотреть коды причин, понять, чего не хватает | В UI должно быть визуально заметно; по политике — не даёт промоутить |
| `fallback` | Сработал аварийный откат | Немедленно сообщить разработчику; результату нельзя доверять | Должен блокировать любое дальнейшее действие над этим объектом |

Бейдж обязан быть виден одновременно на: summary SKU, странице queries SKU, странице generation, в matcher run viewer, на compare-странице.

### `CategoryTierBadge`

Визуальный индикатор `eligibility_tier` категории.

| Tier | Что значит | Что разрешено | Что запрещено |
|---|---|---|---|
| `preview_only` | eval либо не прогонялся, либо не прошёл минимальный порог | Смотреть matcher runs, смотреть сравнения, проектировать candidate query set, записывать human review | Любая форма promote, любое использование candidate как публикуемого результата |
| `eligible_for_preview` / `evaluated` | eval прогнан, метрики в допуске для первого шага | Всё, что выше, плюс promote `preview → candidate` при наличии accepted human review | promote `candidate → approved` запрещён; `approved → published` запрещён всегда |
| `acceptance_passed` / `approved` | eval прошёл по строгому порогу | Всё выше, плюс promote `candidate → approved` при наличии второго accepted human review | promote `approved → published` запрещён всегда (production-генерация выключена) |

### Approval / trust state (на `SeoSkuQuerySet` для candidate path)

- **`approval_state`** — состояние операторского решения по конкретному candidate query set: `draft → preview → candidate → approved`. Это то, что меняет человек через endpoint approval.
- **`trust_state`** — объективный сигнал от eval: `unverified` или `validated`. Этот флаг оператор руками не трогает.

В UI рядом с query set должны быть два отдельных бейджа `ApprovalStateBadge`:
- «Approved by operator» — что конкретно человек решил;
- «Validated by eval» — подтверждено ли объективно.

Они принципиально разные: approved без validated — это «кто-то поверил, но машина не подтвердила»; validated без approved — «машина согласна, но оператор ещё не смотрел». Promote требует обоих.

### Internal lint score

То, что раньше называлось «SEO relevance» / «SEO relevance V2» в карточках генерации, теперь называется **Internal lint (relevance)** и **Internal lint (relevance V2)**.

- Это **диагностический сигнал** о том, насколько сгенерированный текст формально попадает на целевые токены.
- Это **не** качество SEO, **не** метрика ранжирования, **не** критерий публикации.
- В UI под этими блоками должен быть подзаголовок в духе «диагностический сигнал, не является quality gate».
- По нему нельзя принимать решение о promote; gate — это `eligibility_tier` + human review.

Если где-то в UI lint score используется как основание для промоушна или отображается как «оценка качества» — это баг (см. §6).

---

## 3. Ожидаемые экраны

Пути ниже соответствуют реально существующим страницам во `frontend/app/app/project/[projectId]/seo/...`.

> **Навигация (актуально после UI-дополнений).** В шапке `SeoShell` всегда доступны табы **Категории**, **Товары**, **Eval 812**, «Техническая диагностика». Лэндинг `…/seo` содержит сворачиваемый блок «Как пользоваться SEO-модулем». Карточка товара в продукт-листе ведёт сразу на «Запросы», «Compare», «Генерация»; SKU summary линкует на Compare и на последний matcher run (когда он уже спроецирован). Страница «Запросы» содержит два раздела — **Candidate (matcher_v2)** с кнопкой «Обновить candidate» и approval-переключателем, и **Current (legacy path)**.

### 3.1 Страница категории / Eval

Путь: `…/seo/categories/[categoryId]/eval`.

Должно быть видно:
- активный `SeoCategoryProfile` (для 812 — seeded через `scripts/seed_seo_category_profile_812.py`);
- версия активного профиля (`version`) и её `is_active=true`;
- `CategoryTierBadge` с текущим `eligibility_tier`;
- последние метрики eval: `accuracy`, `bad_primary_rate`, `hard_conflict_primary_count`, итоговый `verdict`;
- история eval runs (список `seo_eval_runs` по категории);
- кнопка «Run eval» → `POST /api/v1/projects/{project_id}/seo/eval/matcher/run`;
- статистика по labels (`GET …/seo/eval/labels/stats`) — сколько label-ов, какое покрытие.

Разрешено: запустить eval, посмотреть прошлые runs, открыть детальную run для просмотра.
Запрещено (не должно быть в UI): правка `eligibility_tier` руками, правка `SeoCategoryProfile` руками, правка labels.

Red flag: если после успешного eval `eligibility_tier` не изменился — либо eval упал в preview_only по порогу (ок), либо eval не вызвал харнес как единственного писателя (баг, см. §6).

### 3.2 SKU SEO summary

Путь: `…/seo/products/[nmId]`.

Должно быть видно:
- `QualityBadge` по `summary.quality_mode`;
- ссылка на последний matcher run, если есть (`matcher_run_id` из summary или из candidate query set);
- `CategoryTierBadge` для категории этого SKU;
- `ApprovalStateBadge` для последнего candidate query set (approved? validated?);
- чёткая маркировка, где данные с current-пути, а где с candidate-пути — нельзя показывать их единой кучей.

Запрещено: редактировать `quality_mode`, `degraded_reasons`, `eligibility_tier`, `trust_state` руками — это read-only поля, записываемые сервисным слоем.

### 3.3 Query selection (queries)

Путь: `…/seo/products/[nmId]/queries`.

Должно быть видно:
- candidate projected query set (результат `POST …/query-sets/candidate/project`);
- `approval_state` (draft / preview / candidate / approved);
- `trust_state` (unverified / validated);
- `QualityBadge` от `querySet.quality_mode`;
- `matcher_run_id` — с кликабельной ссылкой в matcher run viewer;
- buckets (primary / secondary / broad / rejected) с составом запросов;
- query-level причины (почему запрос попал в конкретный бакет).

Действия, которые должны быть:
- approve/transition candidate query set (`POST …/query-sets/candidate/{id}/approval`);
- переключение между current и candidate отображением.

Действия, которых быть **не должно**:
- редактирование строк `SeoMatcherResult` (они являются неизменяемым trace-ом);
- редактирование `trust_state` (это только eval пишет);
- перетаскивание запросов между бакетами напрямую в таблице matcher-результатов.

Правка selection_state на уровне элементов `SeoSkuQuerySetItem` — это легаси-поверхность current-пути; на candidate-пути человек меняет **состояние набора** (approval_state), а не перетасовывает отдельные элементы.

### 3.4 Matcher run viewer

Путь: `…/seo/matcher-runs/[runId]`.

Должно быть видно:
- метаданные запуска: `run_id`, `project_id`, `category_id`, `nm_id`, `started_at`, `finished_at`;
- `category_profile_version` — какая версия профиля использовалась;
- `QualityBadge` из run и список `degraded_reasons`;
- buckets: primary / secondary / broad / rejected;
- score components по каждой строке результата;
- matched / missing / conflict атомы по каждому запросу;
- ошибки, если были.

Страница строго **read-only**. Использует только `GET /api/v1/projects/{project_id}/seo/matcher/v2/runs/{run_id}`. Никаких кнопок «re-rank», «edit», «сохранить изменения», «перевести в primary».

Red flag: любой UI-элемент, который POST-ит/PATCH-ит на `seo_matcher_runs` или `seo_matcher_results`, — баг (см. §6).

### 3.5 Matcher compare

Путь: `…/seo/products/[nmId]/compare`.

Должно быть видно:
- результат current path (через существующий `run_meaning_aware_matcher`);
- результат candidate path (через `matcher_v2`);
- per-query bucket diff: **moved to primary**, **moved out of primary**, **newly rejected**;
- agreement rate (как часто current и candidate ставят запрос в один бакет);
- форма human verdict: accept / reject / comment → `POST …/seo/compare/matcher/verdict`.

Страница работает через `GET …/seo/compare/matcher`. Вся страница — read-only над существующими объектами; единственная запись, которая здесь допускается, — это append-only строка в `seo_compare_verdicts`. Никаких изменений buckets, score-ов, quality_mode у current или candidate-ранов от действий на этой странице быть не должно.

Red flag: запись в `seo_matcher_runs`, `seo_matcher_results`, `seo_sku_query_sets` из compare-страницы (см. §6).

### 3.6 Generation

Путь: `…/seo/products/[nmId]/generation`.

Должно быть видно:
- **Research preview banner** наверху страницы, всегда;
- `QualityBadge` из `generation.quality_mode || latest.quality_mode`;
- `matcher_run_id` (ссылка в viewer);
- `content_kind = 'preview'`;
- явный индикатор `publishable = false`;
- карточки Internal lint (relevance) и Internal lint (relevance V2) с подзаголовком о том, что это диагностика, не gate;
- форма human review (`POST …/human-review`): reviewer, verdict (accept/reject), комментарий;
- кнопка Promote с пояснением gate-ов: какой tier нужен, сколько human review accept нужно, какой target_kind возможен.

Поведение кнопок:
- Кнопка «Сгенерировать» **отключена**, пока `SEO_GENERATION_PREVIEW_ENABLED=false`. При false POST на `/generation/run` отдаёт `503`.
- При `SEO_GENERATION_PREVIEW_ENABLED=true` кнопка активна; результат всегда `mode_used='research_preview'`, `publishable=false`, `content_kind='preview'`.
- Кнопка Promote с target_kind `candidate` разрешена только при `eligibility_tier ∈ {evaluated, approved}` + accepted human review — иначе `409` с причиной.
- Promote с target_kind `approved` разрешена только при `eligibility_tier == approved` + ещё один accepted human review.
- Promote с target_kind `published` всегда `409` с причиной `production_generation_off`.

Red flag: кнопка «Опубликовать в WB», статус «Ready to publish», отображение lint score как «Качество SEO» — всё это bugs (см. §6).

### 3.7 Generation compare

Отдельной полноценной compare-страницы генерации в минимальном UI Iteration 2 нет, но endpoint `GET …/seo/compare/generation?category_id=…&nm_id=…` уже живой и используется на compare-странице (раздел «Generation» рядом с matcher-сравнением).

Когда этот блок откроется в UI, он должен:
- показывать текущую (current-путь) версию контента и candidate-версию в двух колонках;
- делать это **read-only**, без кнопок «merge» / «apply» / «перезаписать»;
- единственная запись — human verdict через `POST …/compare/generation/verdict`.

Пока полноценного отдельного экрана нет, нормально, если в UI виден только блок сравнения в рамках общей compare-страницы.

### 3.8 Products list

Путь: `…/seo/products`.

В минимальном виде Iteration 2 ожидается:
- колонка / бейджы `QualityBadge` для SKU, у которых `quality_mode` непустой;
- визуальное предупреждение для SKU с `preview` / `degraded` / `fallback`;
- фильтр по quality-категории (если реализован как часть UI-полиша).

Если квалити-фильтров/бейджей ещё нет — это не баг, а пункт UI-полиша; но показывать SKU «как готовые» без отметки quality тоже нельзя.

---

## 4. End-to-end сценарий на одном SKU в категории 812

Пусть `PROJECT_ID=1`, `CATEGORY_ID=812`, `NM_ID=<конкретный SKU с SeoSkuMeaningAnnotation>`.

1. **Убедиться, что профиль 812 активен.**
   - Клик: открыть страницу `…/seo/categories/812/eval`.
   - Ожидание: виден активный профиль с версией `>=1`, `is_active=true`, есть term groups (expressive, audience, material_constraints).
   - Что не должно происходить: UI не должен предлагать «создать новый профиль» — для 812 он уже seeded.

2. **Запустить eval или посмотреть последний.**
   - Клик: кнопка «Run eval» на eval-странице.
   - Ожидание: появляется новая строка в списке eval runs, с `accuracy`, `bad_primary_rate`, `hard_conflict_primary_count`, `verdict`. После успешного run `CategoryTierBadge` может обновиться (`preview_only → evaluated`, или `evaluated → approved`, или остаться тем же, если метрики не прошли порог).
   - Что не должно происходить: `eligibility_tier` меняется руками; eval исправляет какие-то прошлые строки; eval запускает matcher_v2 в production.

3. **Открыть SKU SEO summary.**
   - Клик: `…/seo/products/{NM_ID}`.
   - Ожидание: виден `QualityBadge`, `CategoryTierBadge`, ссылка на последний matcher run (если есть), `ApprovalStateBadge` по candidate query set.

4. **Запустить/просмотреть candidate matcher.**
   - Клик: кнопка «Project candidate» (или эквивалентный триггер `POST …/query-sets/candidate/project`).
   - Ожидание: создаётся новый `SeoMatcherRun` + `SeoMatcherResult`-ы, создаётся `SeoSkuQuerySet(status='candidate', approval_state='draft', trust_state='unverified')` с `matcher_run_id` и `category_profile_version`.
   - Что не должно происходить: легаси-строка `status='confirmed'` затирается; current path меняется.

5. **Открыть matcher run viewer.**
   - Клик: по `matcher_run_id` переходом на `…/seo/matcher-runs/{runId}`.
   - Ожидание: видны buckets, score components, matched/missing/conflict атомы, `QualityBadge`, `degraded_reasons`, `category_profile_version`. Страница только для чтения.

6. **Проекция candidate matcher → query set.**
   - Уже произошла на шаге 4 (endpoint `candidate/project` выполняет и запуск matcher_v2, и проекцию в query set одной операцией). На экране queries должен появиться новый candidate query set.
   - Что не должно происходить: повторная проекция создаёт второй `status='candidate'` row. Должно быть «at most one `status='candidate'` per (project, category, nm)» — либо upsert в существующий, либо отклонение.

7. **Approve candidate query set.**
   - Клик: «Approve» (кнопка или последовательность: draft → preview → candidate → approved) на странице queries. Это `POST …/query-sets/candidate/{query_set_id}/approval`.
   - Ожидание: `approval_state` переключается на нужный шаг; `trust_state` **не** меняется (он станет `validated` только после eval-прогона, который подтвердит категорию).
   - Что не должно происходить: кнопка approval не пишет ни в какие поля `SeoMatcherResult`.

8. **Сравнить current и candidate.**
   - Клик: `…/seo/products/{NM_ID}/compare`.
   - Ожидание: виден diff по бакетам (moved to primary / out of primary / newly rejected), agreement rate; можно записать verdict. В БД: плюс одна строка в `seo_compare_verdicts`; `seo_matcher_runs` / `seo_matcher_results` — без изменений.

9. **Открыть generation.**
   - Клик: `…/seo/products/{NM_ID}/generation`.
   - Ожидание: виден Research preview banner, `QualityBadge`, `matcher_run_id`, `content_kind=preview`, `publishable=false`. Кнопка «Сгенерировать» отключена, если `SEO_GENERATION_PREVIEW_ENABLED=false`.

10. **Проверить preview-only состояние.**
    - Если флаг выключен: POST на `/generation/run` возвращает `503`; UI-кнопка disabled. Это корректное поведение.

11. **Запустить generation (только на dev/staging с включённым флагом).**
    - Клик: «Сгенерировать».
    - Ожидание: создаётся `SeoGenerationRun` + `SeoContentVersion` с `mode_used='research_preview'`, `publishable=false`, `content_kind='preview'`, `quality_mode` проброшен из candidate query set, `matcher_run_id` тоже проброшен.

12. **Посмотреть сгенерированный контент.**
    - Клик: раскрыть сгенерированные блоки (title/description/bullets по текущему контракту).
    - Ожидание: видны Internal lint (relevance) и Internal lint (relevance V2) как диагностические сигналы, с подписью «не quality gate». Никакой надписи «готово к публикации» быть не должно.

13. **Заполнить human review.**
    - Клик: форма human review → `POST …/human-review` с reviewer, verdict=accept, комментарий.
    - Ожидание: запись попадает в `seo_generation_human_review`, форма отображает факт accept-а.

14. **Попытка promote.**
    - Клик: «Promote» с `target_kind='candidate'`.
    - Ожидание при `eligibility_tier ∈ {evaluated, approved}` + accepted human review: контент переходит в `content_kind='candidate'`.
    - Ожидание при более слабом tier или без accepted human review: `409` с причиной вида `tier_insufficient` или `human_review_missing`.
    - Повторный Promote с `target_kind='approved'`: разрешён только при `eligibility_tier == approved` + ещё один accepted human review.
    - Promote с `target_kind='published'`: всегда `409` с причиной `production_generation_off`. Никакой `content_kind='published'` row в БД появиться не должно.

15. **Проверить, что promote заблокирован/разрешён по верной причине.**
    - Клик: открыть детальный ответ API / UI-сообщение об ошибке.
    - Ожидание: в теле ответа — явный код причины (например, `tier_insufficient`, `human_review_missing`, `production_generation_off`). Это нужно, чтобы оператор понимал, какой gate мешает, и не искал ошибки в случайных местах.

---

## 5. Verification checklist

| Область | Где в UI / API | Ожидаемое поведение | Pass/Fail | Заметки |
|---|---|---|---|---|
| Активный профиль категории 812 | `…/seo/categories/812/eval`; `load_active_profile` в БД | Есть активная запись в `seo_category_profiles` с `is_active=true`, `version>=1`, непустые `term_groups` | | Seed идемпотентный (`scripts/seed_seo_category_profile_812.py`) |
| Запуск eval | Кнопка «Run eval» / `POST …/seo/eval/matcher/run` | 200 с `metrics` и `verdict`; новая строка в `seo_eval_runs` | | |
| `eligibility_tier` меняется только через eval | `SeoCategoryMatchingReadiness.eligibility_tier`; `tests/seo/test_seo_eval_harness.py` | AST-guard ловит любую запись из неразрешённого модуля; в UI нет поля правки tier | | Harness — единственный писатель |
| matcher_v2 создаёт `SeoMatcherRun` + N `SeoMatcherResult` | `POST …/seo/matcher/v2/run` или `POST …/query-sets/candidate/project` | На каждый запуск +1 run и N results; старые run не трогаются | | |
| Matcher run viewer — read-only | `…/seo/matcher-runs/[runId]` | Только GET; никаких кнопок правки, score/buckets неизменяемы | | |
| Проекция candidate не мутирует matcher results | `POST …/query-sets/candidate/project` | Появляется `SeoSkuQuerySet(status='candidate')`; `seo_matcher_results` не меняется | | SQL: нет колонок `approval_state/selection_state/trust_state` в `seo_matcher_results` |
| approved ≠ validated | `ApprovalStateBadge` + `trust_state` в query set | Два разных бейджа; `trust_state` не меняется от `approval` endpoint | | |
| Compare layer — read-only | `…/seo/products/[nmId]/compare`; `tests/seo/test_seo_compare_read_only.py` | GET данных + POST verdict в `seo_compare_verdicts`; нет записи в run/results/query-sets | | |
| Generation — preview only | `…/seo/products/[nmId]/generation` | Always visible Research preview banner; `mode_used='research_preview'`, `publishable=false`, `content_kind='preview'` | | |
| Internal lint ≠ quality | Карточки lint на generation-странице | Подзаголовок «не quality gate»; нет использования как promote-порога | | |
| Promote endpoint уважает gates | `POST …/generation/content/{cv}/promote` | `candidate` требует tier `evaluated+` + accepted review; `approved` требует `approved` + ещё один accepted review; `published` всегда `409` | | |
| Production generation off | `settings.SEO_GENERATION_PREVIEW_ENABLED`, таблица `seo_content_versions` | В prod флаг `false`; `count(*) where content_kind='published' == 0`; нет WB publish endpoint | | |
| Retention | `POST /api/v1/seo/matcher/retention/cleanup?dry_run=…` и `scripts/run_seo_matcher_retention.py --dry-run` | Dry-run выводит план; удаляются только runs вне keep_newest/keep_days и не referenced из non-preview | | |

---

## 6. Red flags и баги

Если в UI наблюдается любое из нижеперечисленного — это баг. Для каждого указано, где, скорее всего, корень и что проверять в первую очередь.

1. **UI говорит «ready» без `QualityBadge`.**
   Опасно: теряется честная маркировка степени доверия; оператор может принять preview / degraded как full.
   Скорее всего: UI-слой (не прокидывается `quality_mode` из summary/queries/generation responses).
   Что проверить: `SeoProductSummaryResponse.quality_mode`, `SeoQuerySetResponse.quality_mode`, `SeoGenerationLatestResponse.quality_mode` — реально ли они не null на этом SKU.

2. **Generation выглядит publishable.**
   Опасно: это прямой путь к выкатыванию research preview как продакшн.
   Скорее всего: либо UI игнорирует `publishable=false`, либо генерация где-то выставляет `publishable=true`.
   Что проверить: `SeoContentVersion.publishable` в БД; `mode_used`; фронтовый код рендеринга кнопок на generation-странице.

3. **Internal lint отображается как «SEO quality score».**
   Опасно: оператор начинает использовать lint как порог promote.
   Скорее всего: UI-слой, не обновлены подписи / подзаголовки карточек.
   Что проверить: тексты на `…/generation/page.tsx` — должны быть «Internal lint (relevance)» и «Internal lint (relevance V2)» + подпись «не quality gate».

4. **Compare-страница меняет buckets/скор.**
   Опасно: read-only инвариант сломан, сравнения становятся недетерминированными.
   Скорее всего: сервис `app.services.seo.compare` или router начали вызывать мутирующие функции.
   Что проверить: `tests/seo/test_seo_compare_read_only.py` — должен оставаться зелёным; ручной обзор `src/app/routers/seo_compare.py` и `src/app/services/seo/compare.py`.

5. **Matcher run viewer разрешает редактирование.**
   Опасно: `SeoMatcherRun` / `SeoMatcherResult` обязаны быть иммутабельным trace-ом.
   Скорее всего: UI добавил форму и какой-то POST, который не должен существовать.
   Что проверить: никаких POST/PATCH из `…/matcher-runs/[runId]/page.tsx`; роутер `seo_matcher_v2` экспонирует только POST run + GET run.

6. **`SeoMatcherResult` имеет operator-editable state.**
   Опасно: trace-таблица превращается в источник операторского состояния и теряет роль системы сравнения.
   Скорее всего: кто-то добавил колонку `approval_state` / `selection_state` / `trust_state` в `seo_matcher_results`.
   Что проверить: SQL `select … from information_schema.columns where table_name='seo_matcher_results'` — не должно быть этих колонок.

7. **Category tier меняется руками в UI.**
   Опасно: ломается единственный writer (`eval.harness`), теряется объективность сигнала.
   Скорее всего: UI-форма, дёргающая нештатный endpoint.
   Что проверить: AST-guard в `tests/seo/test_seo_eval_harness.py`; наличие формы правки tier на eval-странице — её быть не должно.

8. **Production generation может запуститься.**
   Опасно: нарушается фундаментальное ограничение Iteration 2.
   Скорее всего: `SEO_GENERATION_PREVIEW_ENABLED=true` в prod и/или кто-то снял `publishable=false` в `generation.service`.
   Что проверить: значение флага в prod-окружении, содержимое `_coerce_quality_mode` и места, где выставляется `publishable`.

9. **Candidate-результат перетирает current-результат.**
   Опасно: ломается параллельное сосуществование путей, оператор теряет возможность сравнить.
   Скорее всего: проекция candidate не создаёт отдельную строку `status='candidate'`, а апдейтит `status='confirmed'`.
   Что проверить: в БД наличие двух разных строк `SeoSkuQuerySet` на один `(project, category, nm)`, одна `confirmed`, другая `candidate`.

10. **Fallback-результат выглядит как full.**
    Опасно: оператор не отличает аварийный откат от нормы.
    Скорее всего: `QualityBadge` не рендерится для `fallback`, или `degraded_reasons` не отображаются.
    Что проверить: есть ли на странице визуально отличный рендер для `fallback` (цвет + текст причин); tooltip по `degraded_reasons`.

---

## 7. Чего намеренно ещё нет

Нижеприведённые возможности **не реализованы** и не должны ожидаться от UI сейчас. Их отсутствие — не баг.

- **Публикация в Wildberries.** Нет endpoint-а, нет кнопки, `content_kind='published'` всегда запрещён.
- **Batch generation.** Массовый запуск генерации по списку SKU не поддержан; генерация только поштучно на странице SKU.
- **Раскатка на вторую категорию.** Работает только 812 — профиль seeded только для неё, labels только для неё, parity-скрипт только для неё.
- **UI разметки (labeling UI).** Labels импортируются скриптом `scripts/import_seo_eval_labels_812.py`. Интерфейса для ручного редактирования labels в UI нет.
- **Включение production-генерации.** Флаг `SEO_GENERATION_PREVIEW_ENABLED` — только dev/staging переключатель; promote до `published` всегда `409`.
- **Универсальная поддержка любой категории.** `matcher_v2` пока использует часть легаси-хелперов с «категорийными» словарями; CI-гард лишь запрещает новые литералы. Полной категори-агностики ещё нет.
- **Удаление легаси current matcher.** Current path (`run_meaning_aware_matcher`, `status='confirmed'`) намеренно не трогается; его удаление — задача Iteration 3.
- **Profile editor UI.** Редактирование `SeoCategoryProfile` из интерфейса не реализовано; профили обновляются через seed-скрипт.
- **`seo_quality_events`** как отдельная таблица аудита качества — отложено.

---

## 8. CEO-readable summary

- Что можно тестировать сейчас: eval на 812, candidate matcher на 812, matcher run viewer, compare (matcher и базовый generation compare), candidate query set + approval, preview-генерация на dev/staging, human review, promote с gate-ами.
- Чему пока нельзя доверять: качеству любого сгенерированного текста как публикуемого; Internal lint как метрике качества; candidate-результату без подтверждения eval.
- Что обязано оставаться preview: весь `SeoContentVersion` с `content_kind='preview'`, `publishable=false`, `mode_used='research_preview'`; никаких исключений.
- Какие доказательства нужны перед promote: `eligibility_tier == evaluated` (для preview→candidate) или `approved` (для candidate→approved), свежий eval run, accepted human review по каждому шагу, зелёный compare без аномальных перестановок бакетов.
- Approved и validated — разные вещи; promote требует обоих.
- Category tier пишется только eval-харнесом; UI не должен давать его трогать.
- `QualityBadge` обязан быть виден везде, где поле `quality_mode` непустое; его отсутствие в критичных местах — сигнал о баге UI-слоя.
- Compare-страница и matcher run viewer — строго read-only; любая запись оттуда в `seo_matcher_*` или `seo_sku_query_sets` — баг.
- Production-генерация в Iteration 2 остаётся выключенной; promote до `published` всегда возвращает `409 production_generation_off` — это не баг, это инвариант.
- Пока раскатки на категории кроме 812 нет; любые демонстрации на других категориях возможны только как technical preview без каких-либо гарантий.

---

Источники, использованные для этого документа (только чтение):
- `docs/seo-module/implementation-plan/iteration_1/IMPLEMENTATION_REPORT.md`
- `docs/seo-module/implementation-plan/iteration_2/ITERATION_2_IMPLEMENTATION_REPORT.md`
- `docs/seo-module/implementation-plan/iteration_2/ITERATION_2_VERIFICATION_CHECKLIST.md`
- дерево страниц `frontend/app/app/project/[projectId]/seo/**/page.tsx`.
