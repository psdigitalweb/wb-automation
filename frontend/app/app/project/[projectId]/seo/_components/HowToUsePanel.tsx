'use client'

/**
 * HowToUsePanel — compact, collapsible operator help.
 *
 * Placed on the SEO landing page. Intentionally minimal: explains Current vs
 * Candidate, Preview vs Production, Approved vs Validated, badge meanings,
 * and the canonical end-to-end flow. Mirrors
 * `docs/seo-module/implementation-plan/iteration_2/UI_USAGE_AND_VERIFICATION_GUIDE.md`
 * at a glance so operators don't have to leave the app to learn the flow.
 */

import { useState } from 'react'

export function HowToUsePanel({ projectId }: { projectId: string }) {
  const [open, setOpen] = useState(false)
  return (
    <section
      style={{
        border: '1px solid #e2e8f0',
        borderRadius: 8,
        background: '#fff',
        overflow: 'hidden',
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        style={{
          width: '100%',
          textAlign: 'left',
          background: open ? '#f1f5f9' : '#fff',
          border: 0,
          padding: '14px 18px',
          cursor: 'pointer',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          fontWeight: 700,
          fontSize: 16,
          color: '#0f172a',
        }}
      >
        <span>Как пользоваться SEO-модулем</span>
        <span style={{ color: '#64748b', fontWeight: 500 }}>{open ? 'Свернуть' : 'Развернуть'}</span>
      </button>
      {open && (
        <div style={{ padding: '14px 18px 18px', display: 'grid', gap: 14, fontSize: 14, lineHeight: 1.55, color: '#334155' }}>
          <HelpRow
            title="Current vs Candidate"
            body="В production UI операторский шаг один: выбрать запросы и нажать «Сохранить выбор». Внутренние статусы SeoSkuQuerySet остаются только технической совместимостью и не создают отдельный шаг подтверждения."
          />
          <HelpRow
            title="Preview vs Production"
            body="Вся генерация — research preview (content_kind='preview', publishable=false, mode_used='research_preview'). Флаг SEO_GENERATION_PREVIEW_ENABLED только разрешает сам запуск, не превращает результат в publishable. Production-генерации в Iteration 2 нет."
          />
          <HelpRow
            title="Approved vs Validated"
            body="Approved — оператор вручную одобрил candidate query set (approval_state). Validated — eval на размеченном датасете подтвердил категорию (trust_state=validated + eligibility_tier). Это два разных сигнала; promote требует оба."
          />
          <HelpRow
            title="QualityBadge"
            body="full — все сигналы полные, preview — preview-эмбеддер, degraded — есть деградации, fallback — аварийный откат. Бейдж виден на summary / queries / generation / matcher-run / compare."
          />
          <HelpRow
            title="CategoryTierBadge"
            body="preview_only — смотреть можно, promote нельзя. evaluated — разрешён шаг preview→candidate. approved — разрешён candidate→approved. published запрещён всегда. Tier пишется только eval-харнесом."
          />
          <HelpRow
            title="End-to-end поток по одному SKU (категория 812)"
            body={
              <ol style={{ margin: 0, paddingLeft: 18 }}>
                <li>Открыть Eval 812 и (при необходимости) запустить eval.</li>
                <li>Открыть SKU: бейджи Quality / Tier / ApprovalState.</li>
                <li>На Queries нажать «Обновить candidate» (matcher_v2 + проекция).</li>
                <li>Открыть Matcher run viewer — проверить buckets и scoring.</li>
                <li>Открыть Compare — увидеть diff current vs candidate, записать verdict.</li>
                <li>Provoke candidate transitions (draft→preview→candidate→approved).</li>
                <li>Перейти на Generation: Research preview banner + генерация.</li>
                <li>Отправить Human review = accept.</li>
                <li>Promote с target_kind=candidate; при недостаточном tier — 409 с причиной.</li>
                <li>Promote с target_kind=published — всегда 409 production_generation_off.</li>
              </ol>
            }
          />
          <HelpRow
            title="Чего нет и быть не должно"
            body="WB publish, batch generation, вторая категория, profile editor, labeling UI, production-генерация. Если такие кнопки появятся в UI — это баг."
          />
          <div style={{ color: '#64748b', fontSize: 13 }}>
            Подробный разбор и чек-лист верификации: <code>docs/seo-module/implementation-plan/iteration_2/UI_USAGE_AND_VERIFICATION_GUIDE.md</code>.
            {projectId ? null : null}
          </div>
        </div>
      )}
    </section>
  )
}

function HelpRow({ title, body }: { title: string; body: React.ReactNode }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '220px minmax(0, 1fr)', gap: 14 }}>
      <div style={{ fontWeight: 700, color: '#0f172a' }}>{title}</div>
      <div>{body}</div>
    </div>
  )
}
