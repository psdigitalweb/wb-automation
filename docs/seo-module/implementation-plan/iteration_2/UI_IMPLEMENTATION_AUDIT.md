# SEO UI Implementation Audit (Iteration 1 + 2)

Цель этого документа — ответить на вопрос «почему оператор не видит новый UI» и зафиксировать точные пробелы между реально реализованным бэкендом Iteration 1/2 и тем, что оператор может реально нажать.

Аудит проведён по актуальному состоянию веток `frontend/app/app/project/[projectId]/seo/**` и `frontend/lib/apiClient.ts`.

---

## 1. Expected vs Actual

### Маршруты (routes)

| Ожидалось | Фактический файл | Статус | Действие |
|---|---|---|---|
| `/seo` лэндинг | `seo/page.tsx` — 3 карточки | ⚠ навигационный пробел | добавить быстрые ссылки на Eval 812 / мэтчер-раны / «Как пользоваться» |
| `/seo/categories` | `seo/categories/page.tsx` | ⚠ не ведёт на eval | добавить «Eval →» в карточку категории |
| `/seo/categories/[categoryId]` | `seo/categories/[categoryId]/page.tsx` | ⚠ не ведёт на eval | добавить кнопку «Открыть eval» |
| `/seo/categories/[categoryId]/eval` | `seo/categories/[categoryId]/eval/page.tsx` | ✅ реализован, привязан к API | добавлять не нужно, только входы |
| `/seo/products` | `seo/products/page.tsx` | ⚠ только 1 ссылка «Открыть» | добавить быстрые ссылки «Запросы / Compare / Генерация» |
| `/seo/products/[nmId]` (SKU summary) | `seo/products/[nmId]/page.tsx` | ⚠ нет CategoryTier/ApprovalState, нет compare / matcher-run links | дополнить |
| `/seo/products/[nmId]/queries` | `seo/products/[nmId]/queries/page.tsx` | ⚠ candidate-пайплайн не выведен | добавить candidate panel, approval-кнопки, ссылки |
| `/seo/products/[nmId]/compare` | `seo/products/[nmId]/compare/page.tsx` | ✅ реализован, read-only + verdict | навигация: добавить вход с queries/generation/summary |
| `/seo/products/[nmId]/generation` | `seo/products/[nmId]/generation/page.tsx` | ⚠ нет human review / promote / matcher-run link | дополнить |
| `/seo/matcher-runs/[runId]` | `seo/matcher-runs/[runId]/page.tsx` | ✅ read-only viewer | добавить входы из queries/generation/summary |

### Навигация / меню

| Ожидалось | Фактически | Статус | Действие |
|---|---|---|---|
| Таб «Eval» / «Как пользоваться» в SEO shell | `SeoShell` имеет только «Категории», «Товары», «Техническая диагностика» | ⚠ | расширить |
| Ссылка из categories list на eval | нет | ⚠ | добавить |
| Ссылка из категории 812 на eval | нет | ⚠ | добавить |
| Из product list в queries/compare/generation | только «Открыть» → summary | ⚠ | добавить |
| Из SKU summary на compare, matcher-run | только queries/generation | ⚠ | добавить |
| Из queries на matcher-run viewer и compare | нет | ⚠ | добавить |
| Из generation на matcher-run viewer и compare | только «К товару», «К запросам» | ⚠ | добавить |
| Из compare на summary / run viewer | только в queries и eval | ⚠ | добавить |

### apiClient

Все необходимые хелперы уже реализованы. Страницам остаётся только их вызвать.

| Ожидалось | Фактически в `frontend/lib/apiClient.ts` | Статус |
|---|---|---|
| `getSeoMatcherV2Run` | строка 1990 | ✅ |
| `postSeoMatcherEvalRun` | 2516 | ✅ |
| `getSeoEvalRuns` | 2527 | ✅ |
| `getSeoEvalLabelStats` | 2540 | ✅ |
| `postSeoCandidateProject` | 2568 | ✅ |
| `postSeoCandidateApproval` | 2595 | ✅ |
| `postSeoGenerationPromote` | 2619 | ✅ |
| `postSeoGenerationHumanReview` | 2645 | ✅ |
| `getSeoCompareMatcher` | 2674 | ✅ |
| `getSeoCompareGeneration` | 2697 | ✅ |
| `postSeoCompareVerdict` | 2718 | ✅ |
| `getSeoFeatureFlags` | существует; generation gate wired | ✅ |

### Бейджи и компоненты

| Ожидалось | Фактически | Статус |
|---|---|---|
| `QualityBadge` | `seo/_components/QualityBadge.tsx` | ✅ |
| `ResearchPreviewBanner` | там же | ✅ |
| `CategoryTierBadge` | `seo/_components/CategoryTierBadge.tsx` | ✅ |
| `ApprovalStateBadge` (approved vs validated) | там же | ✅ |
| Использование `QualityBadge` на summary/queries/generation | да | ✅ |
| Использование `CategoryTierBadge` на summary | ❌ не использован на SKU summary | ⚠ |
| Использование `ApprovalStateBadge` на queries/summary | ❌ нигде не использован | ⚠ |
| Internal lint надпись вместо «SEO quality score» | на generation — «Internal lint (relevance / V2)» с подписью «диагностический сигнал, не является quality gate» | ✅ |

### Candidate path actions

| Ожидалось | Фактически | Статус |
|---|---|---|
| Кнопка «Спроецировать кандидата» на queries | нет | ❌ |
| Approval transitions (`draft → preview → candidate → approved`) на queries | нет | ❌ |
| Показ candidate meta (matcher_run_id, approval_state, trust_state, category_profile_version, quality_mode) | нет | ❌ |

### Generation actions

| Ожидалось | Фактически | Статус |
|---|---|---|
| Human review form (accept/reject/comment) | нет | ❌ |
| Promote кнопка (candidate / approved / published — с пояснением gate-ов) | нет | ❌ |
| Ссылка на matcher_run viewer по `generation.matcher_run_id` | нет | ❌ |
| Ссылка на compare | нет | ❌ |

### Global help

| Ожидалось | Фактически | Статус |
|---|---|---|
| Короткий in-app help «Как пользоваться» | нет | ❌ |

---

## 2. Диагноз: почему оператор не видит UI

1. Почти все backend-эндпойнты и даже большинство страниц **уже существуют и даже импортируют нужные API-функции**.
2. Но они **недоступны по клику**: на `SeoShell` нет табов «Eval», нет «Как пользоваться», нет ссылок из карточек категорий на eval-страницу. Compare, matcher-run viewer, eval-страница физически есть по URL, но нажать на них из основной навигации нельзя — можно только набрать URL руками.
3. Часть decision-critical действий (candidate projection, approval, promote, human review) не имеют кнопок в UI, хотя endpoints в apiClient уже готовы.
4. SKU summary не показывает `CategoryTierBadge` / `ApprovalStateBadge`, из-за чего «approved vs validated» визуально не существует.

Так что короткий ответ: **экраны были, но были unreachable**, часть действий отсутствовала, плюс некоторые бейджи были не подключены к данным.

---

## 3. Что имплементируем в этой итерации UI-ки

Ниже — минимальный набор изменений, закрывающий observable-слой без нового бэкенда.

1. `seo/_components/SeoShell.tsx` — расширить табы: добавить «Eval 812», «Как пользоваться»; разрешить извне передать дополнительные табы (опциональный `extraTabs`), чтобы страницы могли указывать контекст-зависимые ссылки.
2. `seo/_components/HowToUsePanel.tsx` — новый сворачиваемый блок с кратким руководством (Current vs Candidate, Preview vs Production, Approved vs Validated, бейджи, end-to-end flow). Используется на SEO лэндинге.
3. `seo/page.tsx` — добавить ссылку на Eval 812, на matcher-runs инфо-страницу, встроить `HowToUsePanel`.
4. `seo/categories/page.tsx` — добавить быструю ссылку «Eval» на каждую категорию.
5. `seo/categories/[categoryId]/page.tsx` — добавить кнопку «Открыть eval категории».
6. `seo/products/page.tsx` — добавить ссылки «Запросы», «Compare», «Генерация» в строку товара.
7. `seo/products/[nmId]/page.tsx` (SKU summary) — добавить `CategoryTierBadge` (по eligibility_tier из `getSeoEvalRuns`), `ApprovalStateBadge` (по candidate из `getSeoCompareMatcher`), быстрый блок «Последний matcher run» с прямой ссылкой, ссылки «Compare» и «Matcher run».
8. `seo/products/[nmId]/queries/page.tsx` — добавить Candidate-блок:
   - кнопка «Обновить candidate (matcher_v2 + project)» → `postSeoCandidateProject`;
   - approval transitions → `postSeoCandidateApproval`;
   - бейджи `QualityBadge` + `ApprovalStateBadge` + `CategoryTierBadge`;
   - ссылки на matcher_run viewer и compare.
9. `seo/products/[nmId]/generation/page.tsx` — добавить:
   - ссылку на matcher_run viewer;
   - блок «Human review» с `postSeoGenerationHumanReview`;
   - блок «Promote» с тремя target_kind кнопками и явным объяснением gate-ов (читается как «Preview → Candidate требует eligibility_tier ∈ {evaluated, approved} + accepted human review»).

Мы сознательно не добавляем:

- UI-форму правки профиля категории,
- UI-разметку labels,
- массовую генерацию,
- кнопку публикации в Wildberries.

Эти пункты намеренно вне scope Iteration 2; в UI их появления быть не должно.

---

## 4. Как руками протестировать после фикса

1. Открыть `/app/project/<projectId>/seo` — увидеть help-блок и 4-ю карточку «Eval 812» → клик ведёт на `…/seo/categories/812/eval`.
2. На eval-странице нажать «Запустить eval» и увидеть новую строку в истории с `verdict` и `eligibility_tier_after`.
3. Открыть `…/seo/products?category_id=812`, в строке товара кликнуть «Запросы» → мы на queries; кликнуть «Обновить candidate» → получить `query_set_id` и `matcher_run_id` → увидеть `ApprovalStateBadge` + `QualityBadge` + `CategoryTierBadge` в candidate-блоке.
4. Кликнуть «Matcher run» рядом с candidate-блоком → попасть на `…/seo/matcher-runs/{runId}` без редактируемых элементов.
5. Кликнуть «Compare» → попасть на compare-страницу, прочитать diff и нажать Accept/Reject — верифицировать, что записалось только в `seo_compare_verdicts`.
6. Из queries перейти на Generation. Если `SEO_GENERATION_PREVIEW_ENABLED=false`, кнопка «Сгенерировать» заблокирована — это корректно. Если включено, запустить генерацию.
7. После генерации в новом блоке «Human review» отправить verdict=accept → увидеть id.
8. В блоке «Promote» выбрать `target_kind='candidate'` и нажать Promote. При недостаточном tier / без human review — получить 409 + текст причины. При верных условиях — увидеть `new_content_kind='candidate'`.
9. Попытаться Promote с `target_kind='published'` → всегда 409 `production_generation_off`.

---

## 5. Оставшиеся гэпы (не в этом PR)

- Массовая генерация, labeling UI, profile editor, WB publish — вне scope Iteration 2, оставлены на будущее (как описано в `UI_USAGE_AND_VERIFICATION_GUIDE.md` §7).
- `SeoProductSummaryResponse` сейчас не несёт `matcher_run_id` / `eligibility_tier`. Чтобы отдать эти поля на SKU summary, UI добирает их через уже существующие эндпойнты (`getSeoEvalRuns`, `getSeoCompareMatcher`). Это безопасно, но чуть дороже по запросам — бэкенд может добавить поля в summary в следующей итерации.
- Generation compare отдельной страницы нет; UI добирает статус из блока compare на queries/summary страницах; отдельный `…/generation/compare` экран — задача после Iteration 2 close-out.
