# Operator Workflow — Target UX (v1)

> Статус: **нормативный документ для UI/UX**.
> Парный контекст: `ROADMAP.md` Phase 3 (Production UI), `CATEGORY_PROFILE_SPEC.md`, `CONTEXT_PRIMER.md`.
> Версия: v1 (2026-04-24).

---

## 0. TL;DR

Этот документ описывает **happy path оператора** от установки системы до получения брифа по SKU. Любое UI-изменение сверяется с этим документом: если экран не помогает пройти один из шагов ниже — он должен быть либо удалён, либо перенесён в `/debug/*`.

**Основной поток (5 фаз оператора):**

1. **Onboard category** — залить CSV → дождаться сборки → проверить профиль.
2. **Pick SKU** — выбрать товар для работы.
3. **Review candidates** — посмотреть шортлист запросов, принять/отклонить, при необходимости — просмотреть compare.
4. **Preview draft** — посмотреть preview генерации текста (title/description).
5. **Export brief** — получить готовый бриф в Markdown для копирайтера.

Всё остальное (eval, matcher-run трейс, retention-cleanup, derive-runs history, промоут-диалог, human review form) — debug или admin, не основной поток.

---

## 1. Принципы UX

### 1.1. Контракты, которые должен видеть оператор

| Концепция | Где показывается | Что означает |
|---|---|---|
| **Research Preview vs Production** | Бэйдж вверху экранов с генерацией | Все тексты — research preview, пока оператор явно не нажал «Export brief» |
| **Candidate vs Active profile** | Бэйдж на странице категории | `Active` — применяется сейчас; `Candidate` — свежий derive-run, ещё не активен |
| **Approved vs Under review** | Бэйдж на SKU | `Approved` — оператор подтвердил query-set; `Under review` — ещё нет |
| **Validated quality** | Бэйдж на SKU / category | `Validated` — `eval` подтвердил порог; `Unvalidated` — нет меток или accuracy ниже |
| **Eligibility tier** | Бэйдж на категории | `preview_only | evaluated | approved` — зачем это и что разблокируется |

### 1.2. Жёсткие UX-инварианты

- **Одна цель на экран.** Экран либо информирует, либо просит действия — не оба.
- **Каждый шаг имеет breadcrumb.** Оператор всегда знает, где он в 5-фазном потоке.
- **Отмена = безопасна.** Ни один флоу не создаёт артефактов в БД до явного подтверждения оператора.
- **Preview never confuses with production.** Если экран показывает текст, созданный LLM, — сверху Research preview banner. Без исключений.
- **Ошибка ≠ «Something went wrong».** Каждая ошибка содержит: что случилось, почему, что делать дальше.

### 1.3. Как выглядит «production UI» (visual rules)

- Шапка: логотип + навигация (категории, товары, экспорт), справа — user menu + debug-toggle (если права позволяют).
- Сайдбар только на сложных страницах (category corpus, SKU workbench). На landing — нет.
- Бэйджи группируются: status, quality, eligibility — визуально разделены (цвет, позиция).
- Цветовая семантика:
  - зелёный — approved / validated / passed;
  - жёлтый — pending / building / candidate;
  - красный — rejected / failed;
  - синий — info / preview.

---

## 2. Роли

| Роль | Что делает | Что **не** делает |
|---|---|---|
| **Operator** (основной) | Заливает CSV, смотрит candidate-профили, выбирает SKU, approve'ит queries, экспортирует бриф | Не пишет JSON профиля, не дёргает `/api/seo/matcher/v2/run` напрямую, не редактирует meaning-атомы SKU |
| **Admin** (тот же человек, но с `admin_mode=true`) | Откат профиля, retention-cleanup, force re-derive, управление feature flags | Не правит код |
| **Agent** (AI-исполнитель backend-задач) | Работает по `AGENTS.md`, не трогает UX без явной инструкции | Не заходит на сайт от имени оператора |
| **Copywriter** (вне системы) | Получает бриф, пишет текст, загружает на WB | Не использует это UI напрямую |

---

## 3. Информационная архитектура

### 3.1. Маршруты (целевые, Phase 3)

```
/                                                — landing. Список проектов оператора.
/project/{pid}                                    — project dashboard: quick status всех категорий.

/project/{pid}/category                           — список категорий (active + candidate).
/project/{pid}/category/new                       — wizard: залить CSV + запустить bootstrap + derive.
/project/{pid}/category/{cid}                     — категория: статус, corpus summary, active profile, last derive-run.
/project/{pid}/category/{cid}/sku                 — список SKU категории.

/project/{pid}/sku/{nm_id}                        — SKU workbench (главная рабочая страница).
/project/{pid}/sku/{nm_id}/brief                  — экспорт готового брифа.

/project/{pid}/exports                            — история экспортированных брифов.

/debug/*                                          — всё ниже скрыто за debug-toggle:
  /debug/project/{pid}/category/{cid}/eval        — запуск и результаты eval
  /debug/project/{pid}/category/{cid}/matcher-runs— список/трейс matcher_v2 ранов
  /debug/project/{pid}/category/{cid}/compare     — сравнение current vs candidate матчера
  /debug/project/{pid}/category/{cid}/derive-runs — история derive'ов и их self_check
  /debug/project/{pid}/category/{cid}/profile     — raw JSON активного профиля
  /debug/project/{pid}/category/{cid}/retention   — retention cleanup для matcher-runs

/admin                                            — только для admin-mode:
  /admin/feature-flags
  /admin/rollback
```

### 3.2. Breadcrumbs

Фиксированная схема:
```
Project › <project_name> › Category › <category_name> › SKU › <nm_id> › Brief
```

Каждый элемент — кликабельная ссылка на соответствующую страницу.

---

## 4. Happy path (основной поток)

Ниже — **step-by-step** прохождение одного оператора от «нет ни одной категории» до «экспортировал бриф».

### Phase 4.1 — Onboard category

**Цель:** добавить новую категорию и довести её до `Active profile`.

#### Step 1.1 — Загрузить CSV

Экран: `/project/1/category/new`

UI-элементы:
- Title: «Добавить категорию WB».
- Поле: `Category ID WB` (например, 812).
- Поле: `Название` (опционально, для отображения).
- Загрузка CSV (drag & drop).
- Чекбокс: «Запустить bootstrap автоматически после загрузки» (по умолчанию — включён).

Что происходит после submit:
1. API принимает CSV, создаёт `SeoCategoryImport` job.
2. UI редиректит на `/project/1/category/{cid}?from=new` и показывает статус импорта.
3. На странице категории — progress bar «Обрабатывается» + авто-poll каждые 3 сек (уже реализовано в текущем фронте).

Ошибки:
- Невалидный CSV → явное сообщение: «Колонки X, Y обязательны. У вас: [список]. Пример правильного CSV: <ссылка>».
- Категория уже существует → предложение «Пересоздать corpus» или «Открыть существующую».

#### Step 1.2 — Дождаться bootstrap + derive

Экран: `/project/1/category/{cid}`

Что видит оператор:

```
┌───────────────────────────────────────────────────────────────┐
│ Category 812 "Кружки"                    [ Building… 4/6 ]    │
│ Breadcrumb: Project › EcomCore › Category › 812               │
├───────────────────────────────────────────────────────────────┤
│ Bootstrap progress:                                            │
│ ✓ 1/6 Queries normalized             (31921)                  │
│ ✓ 2/6 Clusters built                 (183)                    │
│ ✓ 3/6 Meanings built                 (87% coverage)           │
│ ✓ 4/6 Category axes computed         (18 subjects)            │
│ ⚙ 5/6 Profile derive                 (running…)               │
│   6/6 Self-check                     (pending)                │
├───────────────────────────────────────────────────────────────┤
│ Last update: 2s ago                                            │
└───────────────────────────────────────────────────────────────┘
```

Все 6 шагов — единая timeline. Автообновление через polling. Нажимать ничего не нужно.

Когда Step 6 = ✓ и `self_check = passed`:
- Progress bar исчезает.
- Появляется «Review candidate profile».

Если `self_check = failed`:
- Progress bar красный.
- Секция «Что не прошло»: список failed-checks с описанием (например, «subject_coverage = 54% (< 70%)» → «Корпус, вероятно, слишком разнородный. Предложения: разделить на под-категории или уточнить primary_subject_hint»).
- Кнопки: `Re-derive with hint` / `Re-derive with different LLM` / `Open raw payload (debug)`.

#### Step 1.3 — Review candidate profile

Экран: `/project/1/category/{cid}` (в режиме «есть candidate»)

UI:
```
┌───────────────────────────────────────────────────────────────┐
│ Category 812 "Кружки"   [Active: v1.812.2026-04-20-auto]      │
│                         [Candidate: v1.812.2026-04-24-auto]   │
├───────────────────────────────────────────────────────────────┤
│ Candidate profile diff vs Active:                              │
│                                                                │
│   subject.primary:            кружка → кружка            (=)   │
│   subject.primary_aliases:    8 → 11                      (+3) │
│   subject.related_but_different:                               │
│     + добавлен: "поильник"                                     │
│   hard_conflicts:             4 → 5                       (+1) │
│   scoring.bucket_cutoffs:     не изменились              (=)   │
│                                                                │
│ Eval smoke (на 191 labels):                                    │
│   accuracy:   0.78 (active) → 0.81 (candidate)   [+0.03]      │
│   primary F1: 0.66 → 0.71                         [+0.05]     │
│                                                                │
│ [Activate candidate]   [Discard candidate]   [View full diff] │
└───────────────────────────────────────────────────────────────┘
```

Действия:
- `Activate candidate` → POST `/api/.../profile/activate` → страница обновляется, показывает новую active-версию.
- `Discard candidate` → устанавливает `is_active=false` для candidate, он остаётся в истории.
- `View full diff` → открывает модалку с полным JSON-diff.

Если candidate не проходит self_check — кнопка `Activate` disabled, tooltip объясняет почему.

#### Step 1.4 — Категория готова

Экран: `/project/1/category/{cid}` (в режиме steady-state)

UI:
```
┌───────────────────────────────────────────────────────────────┐
│ Category 812 "Кружки"   [Active: v1.812.2026-04-24-auto]      │
│                         [Validated: eval accuracy 0.81]        │
│                         [Tier: approved]                       │
├───────────────────────────────────────────────────────────────┤
│ Queries: 31921    Clusters: 183    SKUs: 127                  │
│ Last corpus refresh: 2 дня назад                               │
│ Last derive-run: 4 часа назад                                  │
├───────────────────────────────────────────────────────────────┤
│ [ → Open SKUs ]    [ Refresh corpus ]    [ Debug ]             │
└───────────────────────────────────────────────────────────────┘
```

---

### Phase 4.2 — Pick SKU

**Цель:** выбрать товар для работы.

Экран: `/project/1/category/812/sku`

UI:
- Таблица SKU: `nm_id`, название, Primary image, `Approval state`, `Last run`, `Eligibility tier` (наследуется от категории).
- Фильтры:
  - `Status: all | approved | under review | not yet matched`.
  - `Eligibility: all | preview_only | evaluated | approved`.
  - Search: текстом по названию / nm_id.
- По клику на строку → `/project/1/sku/{nm_id}` (SKU workbench).

Empty state (нет SKU): «SKU появятся после первой синхронизации карточек. Запустить sync now →».

---

### Phase 4.3 — Review candidates (SKU workbench)

**Цель:** получить шортлист запросов для SKU и принять/отклонить.

Экран: `/project/1/sku/{nm_id}`

Это **главная рабочая страница**. UI разделён на 3 секции.

#### Секция 1: SKU summary

```
┌───────────────────────────────────────────────────────────────┐
│ SKU 291861306  "Кружка Капибара Каппи"                        │
│ [Approval: Under review]  [Eligibility: approved]             │
│ Category: 812 "Кружки"                                        │
│                                                                │
│ Meaning summary:                                               │
│   product_type: кружка                                         │
│   audience: женская, детская                                   │
│   style: милая, эстетика                                       │
│   colors: желтый                                               │
│   motifs: капибара                                             │
└───────────────────────────────────────────────────────────────┘
```

«Meaning summary» — это human-readable-представление `SeoSkuMeaningAnnotation` + `SkuAtoms`. Если данных мало — показать warning.

#### Секция 2: Candidate query shortlist

Таблица запросов:
```
┌─────────────────────────────────────────────────────────────────┐
│ Bucket  │ Query                   │ Score │ Reasons │ Action    │
├─────────┼─────────────────────────┼───────┼─────────┼───────────┤
│ primary │ кружка капибара         │ 0.87  │ [ i ]   │ ✓ approve │
│ primary │ милая кружка            │ 0.81  │ [ i ]   │ ✓ approve │
│ primary │ кружка подарок девушке  │ 0.78  │ [ i ]   │ ✓ approve │
│ …       │ …                       │ …     │ …       │ …         │
│secondary│ кружка для кофе         │ 0.55  │ [ i ]   │ ◯ pending │
│ broad   │ кружка керамика         │ 0.32  │ [ i ]   │ ◯ pending │
│ rejected│ кружка для чая мужу     │ —     │ [ i ]   │ ✗ locked  │
└─────────┴─────────────────────────┴───────┴─────────┴───────────┘
```

Поведение:
- По умолчанию все `primary` auto-selected. `secondary` — требует ручного approve. `broad` и `rejected` — по умолчанию не включены.
- `[ i ]` — popover с `matched_atoms`, `missing_atoms`, `conflict_atoms`, `reasons` (из `SeoMatcherResult`).
- Фильтры: по bucket, по тексту, по «только changed since last run».
- Массовые действия: `Approve all primary`, `Reset to defaults`.

Внизу таблицы:
- Статус: `N queries approved / M under review / K rejected by matcher`.
- `[ Save draft ]` — сохраняет текущий выбор в `SeoSkuQuerySet` со `state="draft"`.
- `[ Approve query set ]` — переводит в `state="approved"` + пишет audit-log.

#### Секция 3: Next actions

```
After approval:
  [ → Preview generation ]       (Phase 4.4)
  [ → Compare with previous run ] (debug)
  [ → Export brief (MD) ]        (Phase 4.5, enabled только после approval)
```

---

### Phase 4.4 — Preview draft

Экран: `/project/1/sku/{nm_id}` (секция «Generation preview», раскрывается по клику)

UI:
```
┌───────────────────────────────────────────────────────────────┐
│ 🔵 Research Preview — это черновик, не production-текст.      │
├───────────────────────────────────────────────────────────────┤
│ Title (draft):                                                 │
│   Милая кружка "Капибара Каппи" | Подарок девушке              │
│                                                                │
│ Description (draft):                                           │
│   Уютная жёлтая кружка с милой капибарой. Идеальна для         │
│   подарка — подруге, сестре, коллеге. Керамика, 350 мл.        │
│   [...]                                                        │
│                                                                │
│ Features (draft):                                              │
│   • Материал: керамика                                         │
│   • Объём: 350 мл                                              │
│   • Принт: капибара                                            │
│   • Подходит для: подарок, повседневное использование          │
├───────────────────────────────────────────────────────────────┤
│ [ Regenerate ]   [ Edit manually ]   [ Open generation debug ] │
└───────────────────────────────────────────────────────────────┘
```

Режимы:
- `Regenerate` — другой LLM-прогон с тем же query-set.
- `Edit manually` — раскрывает textarea для правки (не пишет сразу в SKU, только локально до Export).
- `Open generation debug` — ведёт на debug-страницу с raw LLM response, meaning-атомами и trace.

---

### Phase 4.5 — Export brief

Экран: `/project/1/sku/{nm_id}/brief`

UI:
```
┌───────────────────────────────────────────────────────────────┐
│ Brief for SKU 291861306                                        │
│ Generated: 2026-04-24 18:45    [Download .md]  [Copy to clip]  │
├───────────────────────────────────────────────────────────────┤
│ # SKU 291861306 "Кружка Капибара Каппи"                       │
│                                                                │
│ ## Approved queries (12)                                       │
│ ### Primary                                                    │
│   - кружка капибара (score 0.87)                              │
│   - милая кружка (score 0.81)                                 │
│   ...                                                          │
│ ### Secondary                                                  │
│   - кружка для кофе (score 0.55)                              │
│                                                                │
│ ## Draft copy                                                  │
│ Title: Милая кружка "Капибара Каппи" | Подарок девушке         │
│ Description: [...]                                            │
│                                                                │
│ ## Must-cover atoms                                            │
│ - product_type: кружка                                         │
│ - motif: капибара                                              │
│ - color: жёлтый                                                │
│ - expressive: милая, уютная                                    │
│                                                                │
│ ## Must-NOT-cover                                              │
│ - термокружка (subject conflict)                               │
│ - стакан (subject conflict)                                    │
│                                                                │
│ ## Audit                                                       │
│ - Matcher run: #4217 (2026-04-24 18:40)                       │
│ - Profile: v1.812.2026-04-24-auto                              │
│ - Eval verdict: validated (accuracy 0.81)                      │
└───────────────────────────────────────────────────────────────┘
```

По нажатию `Download .md` — скачивается файл `brief_291861306_2026-04-24.md`.

После экспорта:
- Запись в `seo_brief_exports` с `exported_at`, `exported_by`, `brief_markdown_snapshot`, `profile_version`, `matcher_run_id`.
- На `/project/1/exports` появляется новая строка.

---

## 5. Варианты развилок

### 5.1. Оператор загрузил CSV, но bootstrap завис

Симптом: progress bar на Step 3 (meanings) > 10 минут.

UI:
- После 5 мин без прогресса — показать warning: «Обработка занимает дольше обычного. [Посмотреть лог]».
- `[Посмотреть лог]` → debug-экран с `SeoCategoryBootstrapRun.step_statuses`.

### 5.2. Derive не нашёл primary_subject

Симптом: `self_check.subject_coverage = 45%`, failed.

UI:
- На странице категории: красный блок «Derive не смог однозначно определить primary_subject».
- Кнопка `Retry with hint` → модалка: «Подскажите, что является основным товаром этой категории». Оператор вводит, например, `"кружка"`, система пробует derive ещё раз с этим hint.

### 5.3. Candidate profile хуже active по eval

Симптом: accuracy_candidate < accuracy_active.

UI:
- В блоке «Candidate profile diff» — accuracy-сравнение выделено жёлтым.
- Кнопка `Activate candidate` не disabled (формально можно), но рядом warning: «Accuracy на 5 п. п. хуже текущего. Продолжить? [Yes, I know what I'm doing]».

### 5.4. SKU без meaning-атомов

Симптом: SKU workbench показывает «Meaning summary: нет данных».

UI:
- Вместо candidate-списка: карточка «Анализ SKU не выполнен. [Запустить анализ]».
- `[Запустить анализ]` → дёргает SKU-анализ API (тот же, что в текущем iter2-коде).

### 5.5. Eval не пройден (Eligibility = preview_only)

Симптом: у категории `eligibility_tier = preview_only`, Export brief disabled.

UI:
- В Brief-экране: карточка «Категория в статусе preview_only. Бриф доступен как research preview, но не является production-ready».
- Кнопка `Export preview brief` (другой цвет, явно помечен).

---

## 6. Debug-экраны

Доступны через toggle в user menu: `Settings → Developer mode`.

### 6.1. `/debug/project/{pid}/category/{cid}/eval`

- Запуск `eval/matcher/run` вручную.
- Результаты: accuracy, F1 per bucket, таблица labels.
- Сравнение с предыдущими прогонами.

### 6.2. `/debug/project/{pid}/category/{cid}/matcher-runs`

- Список `SeoMatcherRun` (фильтры: по nm_id, по дате, по quality_mode).
- По клику — трейс: eligibility verdict, soft-score components, bucket decision, reasons.

### 6.3. `/debug/project/{pid}/category/{cid}/compare`

- Current vs Candidate для любого SKU (как сейчас реализовано).
- Фильтры бакета, статуса, текстовый поиск (уже сделано в iter2-рефакторе).

### 6.4. `/debug/project/{pid}/category/{cid}/derive-runs`

- История всех derive-ранов (из `seo_category_profile_derive_runs`).
- Для каждого: self_check, diff к предыдущему, eval_baseline/new.

### 6.5. `/debug/project/{pid}/category/{cid}/profile`

- Raw JSON активного профиля + история версий.
- Возможность `rollback`, `download snapshot`.

### 6.6. `/debug/project/{pid}/category/{cid}/retention`

- `matcher-run retention cleanup` (существует в iter2).

---

## 7. Чего оператор НЕ делает руками

- ❌ Не редактирует JSON профиля напрямую.
- ❌ Не правит `seo_meaning_atoms` — атомы автогенерятся через guards.
- ❌ Не запускает matcher_v2 через API — он триггерится автоматически при approve query-set.
- ❌ Не чистит matcher-runs — это admin-задача с retention-флагом.
- ❌ Не пушит бриф обратно на WB — экспортирует MD, передаёт копирайтеру.

Любое желание «нажать на руках эту кнопку» — это сигнал, что в UI чего-то не хватает.

---

## 8. Мэппинг current screens → target

Этот раздел — **для Phase 3**. Агент-исполнитель Phase 3 использует эту таблицу, чтобы решить, что с каждым текущим экраном делать.

| Current URL | Current purpose | Target disposition |
|---|---|---|
| `/app/project/{pid}/seo` | Landing с 3 карточками + HowToUsePanel | **Rewrite** → `/project/{pid}` dashboard (Phase 4.1 entry) |
| `/app/project/{pid}/seo/categories` | Список категорий + Eval 812 | **Rewrite** → `/project/{pid}/category` без Eval-таба |
| `/app/project/{pid}/seo/categories/{cid}` | Corpus status + eval-кнопка | **Rewrite** → Phase 4.1 status + Candidate diff |
| `/app/project/{pid}/seo/categories/{cid}/eval` | Eval results | **Move to** `/debug/.../eval` |
| `/app/project/{pid}/seo/products` | Список SKU | **Rewrite** → `/project/{pid}/category/{cid}/sku` (с scope на категорию) |
| `/app/project/{pid}/seo/products/{nm_id}` | SKU summary | **Rewrite** → SKU workbench (Phase 4.3) |
| `/app/project/{pid}/seo/products/{nm_id}/queries` | Query selection | **Merge into** SKU workbench секция 2 |
| `/app/project/{pid}/seo/products/{nm_id}/generation` | Generation preview + human review + promote | **Split:** preview → workbench секция 3; human review → debug; promote → admin |
| `/app/project/{pid}/seo/products/{nm_id}/compare` | Current vs candidate matcher | **Move to** `/debug/.../compare/{nm_id}` |
| `/app/project/{pid}/seo/matcher-runs/{run_id}` | Matcher-run viewer | **Move to** `/debug/.../matcher-runs/{run_id}` |

Phase 3 выполняется инкрементально:
1. Сначала создаются новые маршруты, старые остаются.
2. Ссылки в sidebar/landing перенаправлены на новые.
3. Старые маршруты помечаются `Deprecated` бэйджем на странице.
4. После одного цикла обратной связи — старые маршруты редиректят на новые.

---

## 9. Minimum viable UX checklist (exit Phase 3)

Phase 3 считается закрытой, когда оператор может пройти happy-path (§4) без:

- [ ] возврата на debug-экраны,
- [ ] использования CLI,
- [ ] открытия консоли браузера,
- [ ] чтения `CATEGORY_PROFILE_SPEC.md`,
- [ ] помощи разработчика.

И:

- [ ] каждый шаг имеет breadcrumb,
- [ ] каждый экран имеет одну явную главную кнопку действия,
- [ ] Research preview banner виден там и только там, где показан LLM-текст,
- [ ] ни один экран не содержит «TODO», «WIP», «Iter2», «debug», «test» в видимом UI.

---

## 10. Agent contract

Для AI-агента, который будет реализовывать Phase 3 UI:

- ✅ Читать этот документ и `CONTEXT_PRIMER.md` **до** любого изменения фронта.
- ✅ Использовать существующие компоненты (`QualityBadge`, `ApprovalStateBadge`, `CategoryTierBadge`, `HowToUsePanel`) — они уже реализованы в iter2.
- ✅ Не создавать новых типов бэйджей, если можно использовать существующие.
- ✅ На каждый новый экран — один `page.tsx` + `_components/` подпапка для локальных компонентов.
- ❌ Не менять backend-контракты.
- ❌ Не удалять существующие API-эндпоинты.
- ❌ Не использовать динамические `any`-типы; TypeScript strict.

---

## 11. Open questions (для обсуждения с оператором до Phase 3)

1. **Массовое апрувлю query-сетов**. Нужно ли оператору approve'ить сразу для 10 SKU разом, или всегда по одному? Предложение: одиночный, но «повторить последний approved pattern» для похожего SKU.
2. **Визуал preview-текста**. Показывать одним куском или с placeholder'ами (`{product_type}`, `{motif}`)? Предложение: полный текст, переключатель в `Edit` раскрывает placeholders.
3. **Экспорт форматов**. Нужно ли `.docx` / `.json` сразу, или достаточно `.md` для MVP? Предложение: `.md` в Phase 4, остальное по запросу.
4. **Много-SKU workbench**. Нужна ли страница «Работа над 10 SKU параллельно»? Предложение: отложить до Phase 5 после обратной связи.

---

## 12. Changelog

- **2026-04-24 v1** — initial. Зафиксирован целевой operator workflow для Phase 3.
