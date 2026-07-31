'use client'

import Link from 'next/link'
import { useMemo, useState, type SyntheticEvent } from 'react'
import {
  getWBProductGroupComparison,
  type WBProductGroupComparisonMember,
  type WBProductGroupComparisonResponse,
  type WBProductGroupMembership,
} from '@/lib/wbProductGroupsApi'
import styles from '../product.module.css'

const integer = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 })
const money = new Intl.NumberFormat('ru-RU', {
  style: 'currency',
  currency: 'RUB',
  maximumFractionDigits: 0,
})

function formatPercent(value: number | null) {
  return value == null ? '—' : `${value.toFixed(1)}%`
}

type SortKey =
  | 'product'
  | 'price'
  | 'impressions'
  | 'ctr'
  | 'opens'
  | 'carts'
  | 'fbo'
  | 'fbs'
  | 'orders'
  | 'revenue'

type SortState = {
  key: SortKey
  direction: 'asc' | 'desc'
}

function getSortValue(
  member: WBProductGroupComparisonMember,
  key: SortKey,
): string | number | null {
  switch (key) {
    case 'product':
      return member.title || member.vendor_code || String(member.nm_id)
    case 'price':
      return member.price.last
    case 'impressions':
      return member.funnel.impressions
    case 'ctr':
      return member.funnel.ctr_percent
    case 'opens':
      return member.funnel.opens
    case 'carts':
      return member.funnel.carts
    case 'fbo':
      return member.stock.fbo
    case 'fbs':
      return member.stock.fbs
    case 'orders':
      return member.funnel.orders
    case 'revenue':
      return member.funnel.revenue
  }
}

function SortableHeader({
  label,
  sortKey,
  sort,
  onSort,
  numeric = false,
}: {
  label: string
  sortKey: SortKey
  sort: SortState | null
  onSort: (key: SortKey) => void
  numeric?: boolean
}) {
  const active = sort?.key === sortKey
  const ariaSort = active
    ? sort.direction === 'asc'
      ? 'ascending'
      : 'descending'
    : 'none'

  return (
    <th
      aria-sort={ariaSort}
      className={numeric ? styles.numericHeader : undefined}
    >
      <button
        type="button"
        className={styles.sortButton}
        onClick={() => onSort(sortKey)}
        title={`Сортировать: ${label}`}
      >
        <span>{label}</span>
        {active ? (
          <span aria-hidden="true" className={styles.sortIndicator}>
            {sort.direction === 'asc' ? '↑' : '↓'}
          </span>
        ) : null}
      </button>
    </th>
  )
}

function ProductIdentity({
  member,
  projectId,
}: {
  member: WBProductGroupComparisonMember
  projectId: string
}) {
  return (
    <div className={styles.groupProduct}>
      {member.image_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={member.image_url} alt="" />
      ) : (
        <span className={styles.groupPhotoPlaceholder}>WB</span>
      )}
      <div>
        <Link
          href={`/app/project/${projectId}/wildberries/catalog/${member.nm_id}`}
        >
          {member.title || `Товар ${member.nm_id}`}
        </Link>
        <small>
          {member.vendor_code || 'Без артикула'} · nmID {member.nm_id}
        </small>
      </div>
    </div>
  )
}

function GroupComparisonTable({
  projectId,
  nmId,
  response,
}: {
  projectId: string
  nmId: number
  response: WBProductGroupComparisonResponse
}) {
  const [sort, setSort] = useState<SortState | null>(null)

  const members = useMemo(() => {
    if (!sort) {
      return response.members
    }

    return [...response.members].sort((left, right) => {
      const leftValue = getSortValue(left, sort.key)
      const rightValue = getSortValue(right, sort.key)

      if (leftValue == null && rightValue == null) return 0
      if (leftValue == null) return 1
      if (rightValue == null) return -1

      const comparison =
        typeof leftValue === 'string' && typeof rightValue === 'string'
          ? leftValue.localeCompare(rightValue, 'ru', {
              numeric: true,
              sensitivity: 'base',
            })
          : Number(leftValue) - Number(rightValue)

      return sort.direction === 'asc' ? comparison : -comparison
    })
  }, [response.members, sort])

  function handleSort(key: SortKey) {
    setSort((current) => {
      if (current?.key === key) {
        return {
          key,
          direction: current.direction === 'asc' ? 'desc' : 'asc',
        }
      }
      return {
        key,
        direction: key === 'product' ? 'asc' : 'desc',
      }
    })
  }

  return (
    <div className={styles.groupTableWrap}>
      <table className={styles.groupTable}>
        <thead>
          <tr>
            <SortableHeader
              label="Товар"
              sortKey="product"
              sort={sort}
              onSort={handleSort}
            />
            <SortableHeader
              label="Цена / СПП"
              sortKey="price"
              sort={sort}
              onSort={handleSort}
              numeric
            />
            <SortableHeader
              label="Показы"
              sortKey="impressions"
              sort={sort}
              onSort={handleSort}
              numeric
            />
            <SortableHeader
              label="CTR"
              sortKey="ctr"
              sort={sort}
              onSort={handleSort}
              numeric
            />
            <SortableHeader
              label="Открытия"
              sortKey="opens"
              sort={sort}
              onSort={handleSort}
              numeric
            />
            <SortableHeader
              label="Корзины"
              sortKey="carts"
              sort={sort}
              onSort={handleSort}
              numeric
            />
            <SortableHeader
              label="Остаток FBO"
              sortKey="fbo"
              sort={sort}
              onSort={handleSort}
              numeric
            />
            <SortableHeader
              label="Остаток FBS"
              sortKey="fbs"
              sort={sort}
              onSort={handleSort}
              numeric
            />
            <SortableHeader
              label="Заказы"
              sortKey="orders"
              sort={sort}
              onSort={handleSort}
              numeric
            />
            <SortableHeader
              label="Выручка"
              sortKey="revenue"
              sort={sort}
              onSort={handleSort}
              numeric
            />
          </tr>
        </thead>
        <tbody>
          {members.map((member) => (
            <tr
              key={member.nm_id}
              className={
                member.nm_id === nmId ? styles.currentGroupProduct : undefined
              }
            >
              <td>
                <ProductIdentity member={member} projectId={projectId} />
              </td>
              <td className={styles.metricCell}>
                <strong>
                  {member.price.last == null
                    ? '—'
                    : money.format(member.price.last)}
                </strong>
                <small>СПП {formatPercent(member.spp.last)}</small>
              </td>
              <td className={styles.metricCell}>
                <strong>{integer.format(member.funnel.impressions)}</strong>
              </td>
              <td className={styles.metricCell}>
                <strong>{formatPercent(member.funnel.ctr_percent)}</strong>
              </td>
              <td className={styles.metricCell}>
                <strong>{integer.format(member.funnel.opens)}</strong>
              </td>
              <td className={styles.metricCell}>
                <strong>{integer.format(member.funnel.carts)}</strong>
              </td>
              <td className={styles.metricCell}>
                <strong>{integer.format(member.stock.fbo)}</strong>
              </td>
              <td className={styles.metricCell}>
                <strong>{integer.format(member.stock.fbs)}</strong>
              </td>
              <td className={styles.metricCell}>
                <strong>{integer.format(member.funnel.orders)}</strong>
              </td>
              <td className={styles.metricCell}>
                <strong>{money.format(member.funnel.revenue)}</strong>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function GroupAnalytics({
  projectId,
  nmId,
  memberships,
  periodFrom,
  periodTo,
}: {
  projectId: string
  nmId: number
  memberships: WBProductGroupMembership[]
  periodFrom: string
  periodTo: string
}) {
  const [responses, setResponses] = useState<
    Record<number, WBProductGroupComparisonResponse>
  >({})
  const [loading, setLoading] = useState<Record<number, boolean>>({})
  const [errors, setErrors] = useState<Record<number, string>>({})

  function loadGroup(
    event: SyntheticEvent<HTMLDetailsElement>,
    membership: WBProductGroupMembership,
  ) {
    if (
      !event.currentTarget.open ||
      responses[membership.wb_group_id] ||
      loading[membership.wb_group_id]
    ) {
      return
    }
    const groupId = membership.wb_group_id
    setLoading((current) => ({ ...current, [groupId]: true }))
    setErrors((current) => ({ ...current, [groupId]: '' }))
    void getWBProductGroupComparison(projectId, groupId, {
      date_from: periodFrom,
      date_to: periodTo,
    })
      .then((response) => {
        setResponses((current) => ({ ...current, [groupId]: response }))
      })
      .catch((error: unknown) => {
        setErrors((current) => ({
          ...current,
          [groupId]:
            error instanceof Error
              ? error.message
              : 'Не удалось загрузить аналитику связки',
        }))
      })
      .finally(() => {
        setLoading((current) => ({ ...current, [groupId]: false }))
      })
  }

  if (memberships.length === 0) {
    return (
      <section className={styles.section}>
        <div className={styles.sectionHeading}>
          <div>
            <h2>Аналитика связки</h2>
            <p>Товар не входит в загруженные связки WB.</p>
          </div>
        </div>
      </section>
    )
  }

  return (
    <section className={styles.section}>
      <div className={styles.sectionHeading}>
        <div>
          <h2>Аналитика связки</h2>
          <p>
            Показатели участников за {periodFrom} — {periodTo}.
          </p>
        </div>
        <Link
          className={styles.secondaryLink}
          href={`/app/project/${projectId}/wildberries/product-groups`}
        >
          Полный отчёт
        </Link>
      </div>

      <div className={styles.accordionList}>
        {memberships.map((membership) => {
          const response = responses[membership.wb_group_id]
          const totals = response?.members.reduce(
            (accumulator, member) => ({
              orders: accumulator.orders + member.funnel.orders,
              revenue: accumulator.revenue + member.funnel.revenue,
            }),
            { orders: 0, revenue: 0 },
          )
          const currentMember = response?.members.find(
            (member) => member.nm_id === nmId,
          )
          const orderShare =
            totals && totals.orders > 0 && currentMember
              ? (currentMember.funnel.orders / totals.orders) * 100
              : null

          return (
            <details
              key={membership.wb_group_id}
              className={styles.accordion}
              onToggle={(event) => loadGroup(event, membership)}
            >
              <summary>
                <span>
                  <strong>Связка {membership.wb_group_id}</strong>
                  <small>{membership.members_count} товаров</small>
                </span>
                <span className={styles.accordionHint}>
                  {totals
                    ? `${integer.format(totals.orders)} заказов · ${money.format(totals.revenue)}`
                    : 'Показать аналитику'}
                </span>
              </summary>

              <div className={styles.accordionBody}>
                {loading[membership.wb_group_id] ? (
                  <div className={styles.inlineStatus}>Загружаем показатели…</div>
                ) : errors[membership.wb_group_id] ? (
                  <div className={styles.inlineError}>
                    {errors[membership.wb_group_id]}
                  </div>
                ) : response ? (
                  <>
                    <div className={styles.groupKpis}>
                      <div>
                        <span>Заказы связки</span>
                        <strong>{integer.format(totals?.orders ?? 0)}</strong>
                      </div>
                      <div>
                        <span>Выручка связки</span>
                        <strong>{money.format(totals?.revenue ?? 0)}</strong>
                      </div>
                      <div>
                        <span>Доля товара в заказах</span>
                        <strong>
                          {orderShare == null ? '—' : `${orderShare.toFixed(1)}%`}
                        </strong>
                      </div>
                    </div>
                    <GroupComparisonTable
                      projectId={projectId}
                      nmId={nmId}
                      response={response}
                    />
                  </>
                ) : null}
              </div>
            </details>
          )
        })}
      </div>
    </section>
  )
}
