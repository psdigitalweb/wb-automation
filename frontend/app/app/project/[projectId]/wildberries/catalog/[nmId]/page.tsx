'use client'

import Link from 'next/link'
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { usePageTitle } from '@/hooks/usePageTitle'
import {
  getWBCatalogProduct,
  type WBCatalogProductResponse,
} from '@/lib/wbCatalogApi'
import {
  getWBContentHistory,
  getWBContentVersion,
  getWBMainPhotoHistory,
  type WBContentSnapshot,
  type WBContentVersion,
  type WBContentVersionSummary,
  type WBMainPhotoPeriod,
} from '@/lib/wbProductContentApi'
import {
  getWBProductGroupsForProduct,
  type WBProductGroupMembership,
} from '@/lib/wbProductGroupsApi'
import { GroupAnalytics } from './_components/GroupAnalytics'
import { CustomerOpinionSection } from './_components/CustomerOpinionSection'
import { ProductSalesChart } from './_components/ProductSalesChart'
import styles from './product.module.css'

const integer = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 })
const money = new Intl.NumberFormat('ru-RU', {
  style: 'currency',
  currency: 'RUB',
  maximumFractionDigits: 0,
})

const contentLabels: Record<string, string> = {
  vendorCode: 'Артикул продавца',
  title: 'Название',
  description: 'Описание',
  subjectID: 'ID категории',
  subjectName: 'Категория',
  dimensions: 'Габариты',
  characteristics: 'Характеристики',
  sizes: 'Размеры',
  photos: 'Фотографии',
  needKiz: 'Маркировка',
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return new Intl.DateTimeFormat('ru-RU', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(parsed)
}

function formatPercent(value: number | null | undefined) {
  return value == null ? '—' : `${value.toFixed(1)}%`
}

function formatRatio(value: number | null | undefined) {
  return value == null ? '—' : `${(value * 100).toFixed(1)}%`
}

function stringifyValue(value: unknown) {
  if (value == null || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'Да' : 'Нет'
  if (typeof value === 'string' || typeof value === 'number') return String(value)
  return JSON.stringify(value, null, 2)
}

function formatCharacteristicValue(value: unknown): string {
  if (value == null || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'Да' : 'Нет'
  if (typeof value === 'number') return String(value)
  if (Array.isArray(value)) {
    const values = value
      .map((item) => formatCharacteristicValue(item))
      .filter((item) => item !== '—')
    return values.length ? values.join(', ') : '—'
  }
  if (typeof value === 'string') {
    const trimmed = value.trim()
    if (
      (trimmed.startsWith('[') && trimmed.endsWith(']')) ||
      (trimmed.startsWith('{') && trimmed.endsWith('}'))
    ) {
      try {
        return formatCharacteristicValue(JSON.parse(trimmed))
      } catch {
        return value
      }
    }
    return value
  }
  if (typeof value === 'object') {
    return Object.entries(value)
      .map(
        ([key, nestedValue]) =>
          `${key}: ${formatCharacteristicValue(nestedValue)}`,
      )
      .join(', ')
  }
  return String(value)
}

function CollapsibleSection({
  title,
  description,
  contentId,
  expanded,
  onToggle,
  children,
}: {
  title: ReactNode
  description: ReactNode
  contentId: string
  expanded: boolean
  onToggle: () => void
  children: ReactNode
}) {
  return (
    <section className={styles.section}>
      <div className={styles.sectionHeading}>
        <div>
          <h2>{title}</h2>
          <p>{description}</p>
        </div>
        <button
          type="button"
          className={styles.collapseButton}
          aria-expanded={expanded}
          aria-controls={contentId}
          aria-label={expanded ? 'Свернуть раздел' : 'Развернуть раздел'}
          title={expanded ? 'Свернуть' : 'Развернуть'}
          onClick={onToggle}
        >
          <span aria-hidden="true">{expanded ? '−' : '+'}</span>
        </button>
      </div>
      {expanded ? <div id={contentId}>{children}</div> : null}
    </section>
  )
}

function ContentSnapshotView({ snapshot }: { snapshot: WBContentSnapshot }) {
  const characteristics = Array.isArray(snapshot.characteristics)
    ? snapshot.characteristics
    : []
  const sizes = Array.isArray(snapshot.sizes) ? snapshot.sizes : []

  return (
    <div className={styles.contentGrid}>
      <div className={styles.descriptionBlock}>
        <span>Описание</span>
        <p>{snapshot.description || 'Описание не заполнено.'}</p>
      </div>
      <dl className={styles.contentFacts}>
        <div>
          <dt>Категория</dt>
          <dd>{snapshot.subjectName || '—'}</dd>
        </div>
        <div>
          <dt>Габариты</dt>
          <dd>{stringifyValue(snapshot.dimensions)}</dd>
        </div>
        <div>
          <dt>Размеры</dt>
          <dd>
            {sizes.length
              ? sizes
                  .map((size) => size.techSize || size.wbSize)
                  .filter(Boolean)
                  .join(', ')
              : '—'}
          </dd>
        </div>
        <div>
          <dt>Маркировка</dt>
          <dd>{stringifyValue(snapshot.needKiz)}</dd>
        </div>
      </dl>
      <div className={styles.characteristics}>
        <span>Характеристики · {characteristics.length}</span>
        {characteristics.length ? (
          <div>
            {characteristics.map((item, index) => {
              const record =
                typeof item === 'object' && item !== null
                  ? (item as Record<string, unknown>)
                  : null
              const name =
                record?.name ?? record?.title ?? `Характеристика ${index + 1}`
              const value =
                record?.value ?? record?.values ?? record?.valueText ?? item
              return (
                <dl key={`${String(name)}-${index}`}>
                  <dt>{String(name)}</dt>
                  <dd>{formatCharacteristicValue(value)}</dd>
                </dl>
              )
            })}
          </div>
        ) : (
          <p>Характеристики отсутствуют.</p>
        )}
      </div>
    </div>
  )
}

function VersionChanges({ version }: { version: WBContentVersion }) {
  const changes = Object.entries(version.changed_fields || {})
  if (!changes.length) return null

  return (
    <div className={styles.versionChanges}>
      <h3>Изменения в версии {version.version_no}</h3>
      <div>
        {changes.map(([field, rawChange]) => {
          const change =
            typeof rawChange === 'object' && rawChange !== null
              ? (rawChange as Record<string, unknown>)
              : {}
          return (
            <article key={field}>
              <strong>{contentLabels[field] || field}</strong>
              <dl>
                <div>
                  <dt>До</dt>
                  <dd>{stringifyValue(change.old)}</dd>
                </div>
                <div>
                  <dt>После</dt>
                  <dd>{stringifyValue(change.new)}</dd>
                </div>
              </dl>
            </article>
          )
        })}
      </div>
    </div>
  )
}

export default function WBCatalogProductPage() {
  const params = useParams()
  const router = useRouter()
  const searchParams = useSearchParams()
  const projectId = typeof params?.projectId === 'string' ? params.projectId : ''
  const nmId = typeof params?.nmId === 'string' ? params.nmId : ''
  usePageTitle(`Товар ${nmId}`, projectId || null)

  const initialPeriod = useMemo(
    () => ({
      from: searchParams.get('period_from') ?? '',
      to: searchParams.get('period_to') ?? '',
    }),
    [searchParams],
  )
  const [periodFrom, setPeriodFrom] = useState(initialPeriod.from)
  const [periodTo, setPeriodTo] = useState(initialPeriod.to)
  const [draftFrom, setDraftFrom] = useState(initialPeriod.from)
  const [draftTo, setDraftTo] = useState(initialPeriod.to)
  const [product, setProduct] = useState<WBCatalogProductResponse | null>(null)
  const [versions, setVersions] = useState<WBContentVersionSummary[]>([])
  const [selectedVersion, setSelectedVersion] =
    useState<WBContentVersion | null>(null)
  const [photoHistory, setPhotoHistory] = useState<WBMainPhotoPeriod[]>([])
  const [memberships, setMemberships] = useState<WBProductGroupMembership[]>([])
  const [contentExpanded, setContentExpanded] = useState(false)
  const [photoExpanded, setPhotoExpanded] = useState(false)
  const [opinionExpanded, setOpinionExpanded] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadProduct = useCallback(
    async (from: string, to: string) => {
      if (!projectId || !nmId) return
      setLoading(true)
      setError(null)
      try {
        const response = await getWBCatalogProduct(projectId, nmId, {
          period_from: from || undefined,
          period_to: to || undefined,
        })
        setProduct(response)
        if (!from && !to) {
          setPeriodFrom(response.period_from)
          setPeriodTo(response.period_to)
          setDraftFrom(response.period_from)
          setDraftTo(response.period_to)
          router.replace(
            `/app/project/${projectId}/wildberries/catalog/${nmId}?period_from=${response.period_from}&period_to=${response.period_to}`,
            { scroll: false },
          )
        }
      } catch (caught: unknown) {
        setError(
          typeof caught === 'object' &&
            caught !== null &&
            'detail' in caught &&
            typeof caught.detail === 'string'
            ? caught.detail
            : 'Не удалось загрузить товар',
        )
      } finally {
        setLoading(false)
      }
    },
    [nmId, projectId, router],
  )

  useEffect(() => {
    void loadProduct(periodFrom, periodTo)
  }, [loadProduct, periodFrom, periodTo])

  useEffect(() => {
    if (!projectId || !nmId) return
    let cancelled = false
    void Promise.all([
      getWBContentHistory(projectId, nmId),
      getWBMainPhotoHistory(projectId, nmId),
      getWBProductGroupsForProduct(projectId, nmId),
    ])
      .then(async ([history, photos, groups]) => {
        if (cancelled) return
        setVersions(history)
        setPhotoHistory(photos)
        setMemberships(groups)
        if (history.length) {
          const latest = await getWBContentVersion(
            projectId,
            nmId,
            history[0].id,
          )
          if (!cancelled) setSelectedVersion(latest)
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(
            caught instanceof Error
              ? caught.message
              : 'Не удалось загрузить историю товара',
          )
        }
      })
    return () => {
      cancelled = true
    }
  }, [nmId, projectId])

  function applyPeriod() {
    if (!draftFrom || !draftTo || draftFrom > draftTo) {
      setError('Проверьте выбранный период')
      return
    }
    setPeriodFrom(draftFrom)
    setPeriodTo(draftTo)
    router.replace(
      `/app/project/${projectId}/wildberries/catalog/${nmId}?period_from=${draftFrom}&period_to=${draftTo}`,
      { scroll: false },
    )
  }

  async function selectVersion(version: WBContentVersionSummary) {
    setError(null)
    try {
      setSelectedVersion(
        await getWBContentVersion(projectId, nmId, version.id),
      )
      setContentExpanded(true)
    } catch {
      setError('Не удалось загрузить выбранную версию контента')
    }
  }

  if (loading && !product) {
    return <main className={styles.status}>Загружаем товар…</main>
  }

  if (!product) {
    return (
      <main className={`${styles.status} ${styles.error}`}>
        {error || 'Товар не найден'}
      </main>
    )
  }

  const item = product.item

  return (
    <main className={styles.page}>
      <div className={styles.breadcrumbs}>
        <Link href={`/app/project/${projectId}/wildberries/catalog`}>
          ← Каталог товаров
        </Link>
        <span>/</span>
        <span>nmID {item.nm_id}</span>
      </div>

      <section className={styles.hero}>
        <div className={styles.heroPhoto}>
          {item.main_photo_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={item.main_photo_url} alt="" />
          ) : (
            <span>Нет фото</span>
          )}
        </div>
        <div className={styles.heroIdentity}>
          <div className={styles.eyebrow}>Wildberries · Товар</div>
          <h1>{item.title || 'Без названия'}</h1>
          <div className={styles.identityMeta}>
            <span>{item.vendor_code || 'Без артикула'}</span>
            <span>nmID {item.nm_id}</span>
            <span className={styles.activity}>
              <i className={item.is_active ? styles.activeDot : undefined} />
              {item.is_active ? 'Активен на витрине' : 'Активность не подтверждена'}
            </span>
          </div>
          <a
            className={styles.wbLink}
            href={`https://www.wildberries.ru/catalog/${item.nm_id}/detail.aspx`}
            target="_blank"
            rel="noreferrer"
          >
            Открыть на Wildberries ↗
          </a>
        </div>
        <div className={styles.periodCard}>
          <strong>Период показателей</strong>
          <label>
            С
            <input
              type="date"
              value={draftFrom}
              onChange={(event) => setDraftFrom(event.target.value)}
            />
          </label>
          <label>
            По
            <input
              type="date"
              value={draftTo}
              onChange={(event) => setDraftTo(event.target.value)}
            />
          </label>
          <button type="button" onClick={applyPeriod} disabled={loading}>
            {loading ? 'Обновляем…' : 'Применить'}
          </button>
        </div>
      </section>

      {error ? <div className={styles.errorBanner}>{error}</div> : null}

      <section className={styles.kpiGrid}>
        <article>
          <span>Цена на витрине</span>
          <strong>
            {item.showcase_price == null ? '—' : money.format(item.showcase_price)}
          </strong>
          <small>
            СПП {formatPercent(item.spp_percent)} · РРЦ{' '}
            {item.rrp_price == null ? '—' : money.format(item.rrp_price)}
          </small>
          <small>
            Скидка продавца {formatPercent(item.seller_discount_percent)}
          </small>
        </article>
        <article>
          <span>Рейтинг и отзывы</span>
          <strong>{item.rating == null ? '★ —' : `★ ${item.rating.toFixed(1)}`}</strong>
          <small>{integer.format(item.reviews_count)} отзывов</small>
          <a
            className={styles.opinionKpiLink}
            href="#customer-opinion-section"
            onClick={() => setOpinionExpanded(true)}
          >
            Что говорят покупатели
          </a>
        </article>
        <article>
          <span>Охват</span>
          <strong>{integer.format(item.impressions)}</strong>
          <small>
            {integer.format(item.card_clicks)} переходов · CTR{' '}
            {formatPercent(item.ctr_percent)}
          </small>
        </article>
        <article>
          <span>Заказы</span>
          <strong>{money.format(item.order_sum)}</strong>
          <small>{integer.format(item.order_count)} заказов</small>
        </article>
        <article>
          <span>Выкупы</span>
          <strong>{money.format(item.buyout_sum)}</strong>
          <small>{integer.format(item.buyout_count)} выкупов</small>
        </article>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHeading}>
          <div>
            <h2>Воронка товара</h2>
            <p>
              Показатели за {product.period_from} — {product.period_to}.
            </p>
          </div>
        </div>
        <div className={styles.funnel}>
          <div>
            <span>Показы</span>
            <strong>{integer.format(item.impressions)}</strong>
          </div>
          <div>
            <span>Переходы</span>
            <strong>{integer.format(item.card_clicks)}</strong>
            <small>{formatPercent(item.ctr_percent)}</small>
          </div>
          <div>
            <span>Открытия</span>
            <strong>{integer.format(item.opens)}</strong>
          </div>
          <div>
            <span>Корзины</span>
            <strong>{integer.format(item.cart_count)}</strong>
            <small>{formatRatio(item.cart_rate)}</small>
          </div>
          <div>
            <span>Заказы</span>
            <strong>{integer.format(item.order_count)}</strong>
            <small>{formatRatio(item.cart_to_order_rate)}</small>
          </div>
          <div>
            <span>Выкупы</span>
            <strong>{integer.format(item.buyout_count)}</strong>
          </div>
        </div>
      </section>

      <ProductSalesChart
        projectId={projectId}
        nmId={item.nm_id}
        periodFrom={product.period_from}
        periodTo={product.period_to}
        versions={versions}
      />

      <CustomerOpinionSection
        projectId={projectId}
        nmId={item.nm_id}
        expanded={opinionExpanded}
        onToggle={() => setOpinionExpanded((current) => !current)}
      />

      <CollapsibleSection
        title={
          selectedVersion &&
          versions.length > 0 &&
          selectedVersion.id !== versions[0].id
            ? `Контент версии ${selectedVersion.version_no}`
            : 'Текущий контент'
        }
        description={
          selectedVersion
            ? `Версия ${selectedVersion.version_no} · обнаружена ${formatDateTime(selectedVersion.observed_at)}`
            : 'История контента ещё не собрана.'
        }
        contentId="current-content-section"
        expanded={contentExpanded}
        onToggle={() => setContentExpanded((current) => !current)}
      >
        {selectedVersion ? (
          <>
            <ContentSnapshotView snapshot={selectedVersion.content_snapshot} />
            <VersionChanges version={selectedVersion} />
          </>
        ) : (
          <div className={styles.inlineStatus}>Нет сохранённых версий контента.</div>
        )}
      </CollapsibleSection>

      <section className={styles.section}>
        <div className={styles.sectionHeading}>
          <div>
            <h2>История изменений</h2>
            <p>{versions.length} сохранённых версий.</p>
          </div>
        </div>
        {versions.length ? (
          <div className={styles.versionList}>
            {versions.map((version) => {
              const changed = Object.keys(version.changed_fields || {})
              const selected = selectedVersion?.id === version.id
              return (
                <button
                  key={version.id}
                  type="button"
                  className={selected ? styles.selectedVersion : undefined}
                  onClick={() => selectVersion(version)}
                >
                  <span>
                    <strong>Версия {version.version_no}</strong>
                    <small>{formatDateTime(version.observed_at)}</small>
                  </span>
                  <span className={styles.changedFields}>
                    {version.event_type === 'initial'
                      ? 'Стартовая версия'
                      : changed.length
                        ? changed
                            .map((field) => contentLabels[field] || field)
                            .join(', ')
                        : 'Изменение контента'}
                  </span>
                </button>
              )
            })}
          </div>
        ) : (
          <div className={styles.inlineStatus}>Изменений пока нет.</div>
        )}
      </section>

      <CollapsibleSection
        title="История главного фото"
        description="Периоды использования и результат локального архивирования."
        contentId="main-photo-history-section"
        expanded={photoExpanded}
        onToggle={() => setPhotoExpanded((current) => !current)}
      >
        {photoHistory.length ? (
          <div className={styles.photoHistory}>
            {photoHistory.map((period) => (
              <article key={period.id}>
                {period.source_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={period.source_url} alt="" />
                ) : (
                  <div>Нет фото</div>
                )}
                <strong>{formatDateTime(period.observed_from)}</strong>
                <small>
                  {period.observed_to
                    ? `до ${formatDateTime(period.observed_to)}`
                    : 'Текущее фото'}
                </small>
                <span data-status={period.archive_status}>
                  {period.archive_status === 'stored'
                    ? 'Архивировано'
                    : period.archive_status === 'failed'
                      ? 'Ошибка архива'
                      : period.archive_status === 'skipped_inactive'
                        ? 'Неактивный товар'
                        : 'Ожидает архивации'}
                </span>
              </article>
            ))}
          </div>
        ) : (
          <div className={styles.inlineStatus}>История фото пока отсутствует.</div>
        )}
      </CollapsibleSection>

      <GroupAnalytics
        key={`${periodFrom}:${periodTo}`}
        projectId={projectId}
        nmId={item.nm_id}
        memberships={memberships}
        periodFrom={product.period_from}
        periodTo={product.period_to}
      />
    </main>
  )
}
