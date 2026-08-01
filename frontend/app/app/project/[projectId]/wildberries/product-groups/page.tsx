'use client'

import { FormEvent, Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import { useParams } from 'next/navigation'
import {
  getWBProductGroupCategories,
  getWBProductGroupComparison,
  getWBProductGroups,
  getWBProductGroupSeries,
  type WBProductGroupCategory,
  type WBProductGroupComparisonMember,
  type WBProductGroupListItem,
  type WBProductGroupSeriesItem,
} from '@/lib/wbProductGroupsApi'
import ComparisonChart from './_components/ComparisonChart'
import styles from './product-groups.module.css'
import { useConstrainedReportPeriod } from '@/hooks/useReportFilterOptions'
import { ReportDataCoverage } from '@/components/ui-v2/ReportDataCoverage'

type SortKey =
  | 'nm_id'
  | 'price'
  | 'spp'
  | 'impressions'
  | 'ctr'
  | 'opens'
  | 'carts'
  | 'orders'
  | 'revenue'

const GROUPS_PAGE_SIZE = 50

function localDate(value: Date): string {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function defaultPeriod(): { dateFrom: string; dateTo: string } {
  const end = new Date()
  const start = new Date()
  start.setDate(end.getDate() - 29)
  return { dateFrom: localDate(start), dateTo: localDate(end) }
}

const formatInt = (value: number) => new Intl.NumberFormat('ru-RU').format(value)
const formatMoney = (value: number | null) =>
  value == null ? '—' : `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(value)} ₽`
const formatPct = (value: number | null) => (value == null ? '—' : `${value.toFixed(1)}%`)
const formatDateTime = (value: string) =>
  new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))

function sortValue(member: WBProductGroupComparisonMember, key: SortKey): number {
  switch (key) {
    case 'nm_id':
      return member.nm_id
    case 'price':
      return member.price.last ?? Number.NEGATIVE_INFINITY
    case 'spp':
      return member.spp.last ?? Number.NEGATIVE_INFINITY
    case 'impressions':
      return member.funnel.impressions
    case 'ctr':
      return member.funnel.ctr_percent ?? Number.NEGATIVE_INFINITY
    case 'opens':
      return member.funnel.opens
    case 'carts':
      return member.funnel.carts
    case 'orders':
      return member.funnel.orders
    case 'revenue':
      return member.funnel.revenue
  }
}

export default function WBProductGroupsPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const initialPeriod = useMemo(defaultPeriod, [])
  const [search, setSearch] = useState('')
  const [appliedSearch, setAppliedSearch] = useState('')
  const [category, setCategory] = useState('')
  const [inStock, setInStock] = useState(false)
  const [categories, setCategories] = useState<WBProductGroupCategory[]>([])
  const [groups, setGroups] = useState<WBProductGroupListItem[]>([])
  const [groupsTotal, setGroupsTotal] = useState(0)
  const [groupsPage, setGroupsPage] = useState(1)
  const [selectedGroupId, setSelectedGroupId] = useState<number | null>(null)
  const [members, setMembers] = useState<WBProductGroupComparisonMember[]>([])
  const [selectedNmIds, setSelectedNmIds] = useState<number[]>([])
  const [series, setSeries] = useState<WBProductGroupSeriesItem[]>([])
  const [dateFrom, setDateFrom] = useState(initialPeriod.dateFrom)
  const [dateTo, setDateTo] = useState(initialPeriod.dateTo)
  const [sortKey, setSortKey] = useState<SortKey>('orders')
  const [sortDesc, setSortDesc] = useState(true)
  const [loadingGroups, setLoadingGroups] = useState(true)
  const [loadingComparison, setLoadingComparison] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { options: reportOptions } = useConstrainedReportPeriod(
    projectId, 'product-groups', dateFrom, dateTo, setDateFrom, setDateTo,
  )

  const loadGroups = useCallback(
    async (query = '', page = 1, selectedCategory = '', onlyInStock = false) => {
      setLoadingGroups(true)
      setError(null)
      try {
        const response = await getWBProductGroups(projectId, {
          search: query,
          category: selectedCategory,
          in_stock: onlyInStock,
          page,
          page_size: GROUPS_PAGE_SIZE,
        })
        setGroups(response.items)
        setGroupsTotal(response.total)
        setGroupsPage(response.page)
        setSelectedGroupId((current) => {
          if (current != null && response.items.some((item) => item.wb_group_id === current)) return current
          return null
        })
      } catch (requestError) {
        setError(requestError instanceof Error ? requestError.message : 'Не удалось загрузить связки')
      } finally {
        setLoadingGroups(false)
      }
    },
    [projectId]
  )

  useEffect(() => {
    void loadGroups()
  }, [loadGroups])

  useEffect(() => {
    let cancelled = false
    void getWBProductGroupCategories(projectId)
      .then((items) => {
        if (!cancelled) setCategories(items)
      })
      .catch((requestError) => {
        if (!cancelled) setError(requestError instanceof Error ? requestError.message : 'Не удалось загрузить категории')
      })
    return () => {
      cancelled = true
    }
  }, [projectId])

  useEffect(() => {
    if (selectedGroupId == null) {
      setMembers([])
      return
    }
    let cancelled = false
    setLoadingComparison(true)
    setError(null)
    void getWBProductGroupComparison(projectId, selectedGroupId, {
      date_from: dateFrom,
      date_to: dateTo,
    })
      .then((response) => {
        if (cancelled) return
        setMembers(response.members)
        setSelectedNmIds((current) => {
          const allowed = new Set(response.members.map((member) => member.nm_id))
          const retained = current.filter((nmId) => allowed.has(nmId)).slice(0, 5)
          if (retained.length > 0) return retained
          return [...response.members]
            .sort((left, right) => right.funnel.orders - left.funnel.orders)
            .slice(0, Math.min(3, response.members.length))
            .map((member) => member.nm_id)
        })
      })
      .catch((requestError) => {
        if (!cancelled) setError(requestError instanceof Error ? requestError.message : 'Не удалось загрузить сравнение')
      })
      .finally(() => {
        if (!cancelled) setLoadingComparison(false)
      })
    return () => {
      cancelled = true
    }
  }, [dateFrom, dateTo, projectId, selectedGroupId])

  useEffect(() => {
    if (selectedGroupId == null || selectedNmIds.length === 0) {
      setSeries([])
      return
    }
    let cancelled = false
    void getWBProductGroupSeries(projectId, selectedGroupId, {
      date_from: dateFrom,
      date_to: dateTo,
      nm_ids: selectedNmIds,
    })
      .then((response) => {
        if (!cancelled) setSeries(response.series)
      })
      .catch((requestError) => {
        if (!cancelled) setError(requestError instanceof Error ? requestError.message : 'Не удалось загрузить графики')
      })
    return () => {
      cancelled = true
    }
  }, [dateFrom, dateTo, projectId, selectedGroupId, selectedNmIds])

  const sortedMembers = useMemo(
    () =>
      [...members].sort((left, right) => {
        const delta = sortValue(left, sortKey) - sortValue(right, sortKey)
        return sortDesc ? -delta : delta
      }),
    [members, sortDesc, sortKey]
  )

  function submitSearch(event: FormEvent) {
    event.preventDefault()
    const query = search.trim()
    setAppliedSearch(query)
    void loadGroups(query, 1, category, inStock)
  }

  function changeGroupsPage(nextPage: number) {
    setSelectedGroupId(null)
    void loadGroups(appliedSearch, nextPage, category, inStock)
  }

  function changeCategory(nextCategory: string) {
    setCategory(nextCategory)
    setSelectedGroupId(null)
    void loadGroups(appliedSearch, 1, nextCategory, inStock)
  }

  function changeInStock(nextValue: boolean) {
    setInStock(nextValue)
    setSelectedGroupId(null)
    void loadGroups(appliedSearch, 1, category, nextValue)
  }

  function changeSort(next: SortKey) {
    if (sortKey === next) {
      setSortDesc((value) => !value)
      return
    }
    setSortKey(next)
    setSortDesc(true)
  }

  function toggleMember(nmId: number) {
    setSelectedNmIds((current) => {
      if (current.includes(nmId)) return current.filter((value) => value !== nmId)
      if (current.length >= 5) return current
      return [...current, nmId]
    })
  }

  function toggleGroup(groupId: number) {
    setSelectedNmIds([])
    setSeries([])
    setError(null)
    setSelectedGroupId((current) => (current === groupId ? null : groupId))
  }

  const header = (label: string, key: SortKey) => (
    <button type="button" className={styles.sortButton} onClick={() => changeSort(key)}>
      {label} {sortKey === key ? (sortDesc ? '↓' : '↑') : ''}
    </button>
  )

  const groupsTotalPages = Math.max(1, Math.ceil(groupsTotal / GROUPS_PAGE_SIZE))
  const groupsRangeStart = groupsTotal === 0 ? 0 : (groupsPage - 1) * GROUPS_PAGE_SIZE + 1
  const groupsRangeEnd = Math.min(groupsPage * GROUPS_PAGE_SIZE, groupsTotal)

  return (
    <main className={styles.page}>
      <header className={styles.pageHeader}>
        <div>
          <div className={styles.eyebrow}>Wildberries · Отчёты</div>
          <h1>Аналитика связок</h1>
          <p>Сравнение воронки, цен и СПП каждого товара внутри объединённой карточки WB.</p>
        </div>
        <div className={styles.period}>
          <label>
            С
            <input type="date" value={dateFrom} min={reportOptions?.date_filter.min_date ?? undefined} max={dateTo || reportOptions?.date_filter.max_date || undefined} onChange={(event) => setDateFrom(event.target.value)} />
          </label>
          <label>
            По
            <input type="date" value={dateTo} min={dateFrom || reportOptions?.date_filter.min_date || undefined} max={reportOptions?.date_filter.max_date ?? undefined} onChange={(event) => setDateTo(event.target.value)} />
          </label>
        </div>
      </header>
      <ReportDataCoverage options={reportOptions} periodFrom={dateFrom} periodTo={dateTo} />

      {error ? <div className={styles.error}>{error}</div> : null}

      <section className={styles.groupsSection}>
        <div className={styles.groupsToolbar}>
          <form onSubmit={submitSearch} className={styles.searchForm}>
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Найти по nmID, артикулу, названию или ID связки"
            />
            <select
              value={category}
              onChange={(event) => changeCategory(event.target.value)}
              aria-label="Категория WB"
            >
              <option value="">Все категории</option>
              {categories.map((item) => (
                <option key={item.name} value={item.name}>
                  {item.name} · {formatInt(item.groups_count)}
                </option>
              ))}
            </select>
            <label className={styles.stockToggle}>
              <input
                type="checkbox"
                checked={inStock}
                onChange={(event) => changeInStock(event.target.checked)}
              />
              В наличии
            </label>
            <button type="submit">Найти</button>
          </form>
          <span>{groupsTotal ? `${formatInt(groupsTotal)} связок` : 'Связок нет'}</span>
        </div>
        {loadingGroups ? (
          <div className={styles.empty}>Загружаем связки…</div>
        ) : groups.length === 0 ? (
          <div className={styles.empty}>Связки не найдены. Запустите загрузку «Связки товаров WB».</div>
        ) : (
          <>
            <div className={styles.groupsTableScroller}>
              <table className={styles.groupsTable}>
              <thead>
                <tr>
                  <th>Связка</th>
                  <th>Товары</th>
                  <th>FBO</th>
                  <th>FBS</th>
                  <th>Обновлена</th>
                  <th aria-label="Раскрыть связку" />
                </tr>
              </thead>
              <tbody>
                {groups.map((group) => {
                  const expanded = group.wb_group_id === selectedGroupId
                  return (
                    <Fragment key={group.wb_group_id}>
                      <tr className={expanded ? styles.groupRowExpanded : styles.groupRow}>
                        <td>
                          <button
                            type="button"
                            className={styles.groupIdentity}
                            onClick={() => toggleGroup(group.wb_group_id)}
                            aria-expanded={expanded}
                          >
                            <span>
                              <strong>Связка {group.wb_group_id}</strong>
                              <small>
                                {group.previews
                                  .map((preview) => preview.vendor_code || preview.title || preview.nm_id)
                                  .slice(0, 3)
                                  .join(' · ')}
                              </small>
                            </span>
                          </button>
                        </td>
                        <td>
                          <div className={styles.groupComposition}>
                            <div className={styles.productStack} aria-hidden="true">
                              {group.previews.slice(0, 4).map((preview, index) =>
                                preview.image_url ? (
                                  // eslint-disable-next-line @next/next/no-img-element
                                  <img
                                    key={preview.nm_id}
                                    src={preview.image_url}
                                    alt=""
                                    style={{ zIndex: 5 - index }}
                                  />
                                ) : (
                                  <span key={preview.nm_id} style={{ zIndex: 5 - index }}>
                                    WB
                                  </span>
                                )
                              )}
                            </div>
                            <span>
                              <strong>{group.members_count}</strong>
                              <small>товаров</small>
                            </span>
                          </div>
                        </td>
                        <td className={styles.stockCell}>{formatInt(group.fbo_stock_qty)}</td>
                        <td className={styles.stockCell}>{formatInt(group.fbs_stock_qty)}</td>
                        <td className={styles.updatedCell}>{formatDateTime(group.last_seen_at)}</td>
                        <td className={styles.expandCell}>
                          <button
                            type="button"
                            className={styles.expandButton}
                            onClick={() => toggleGroup(group.wb_group_id)}
                            aria-label={expanded ? 'Свернуть связку' : 'Раскрыть связку'}
                          >
                            {expanded ? 'Свернуть' : 'Сравнить'}
                          </button>
                        </td>
                      </tr>
                      {expanded ? (
                        <tr className={styles.expandedRow}>
                          <td colSpan={6}>
                            <div className={styles.expandedPanel}>
                              <div className={styles.sectionHeader}>
                                <div>
                                  <h2>Товары связки {group.wb_group_id}</h2>
                                  <p>
                                    {group.members_count} товаров · выбрано для графиков {selectedNmIds.length} из 5
                                  </p>
                                </div>
                                <span className={styles.hint}>Показатели рассчитаны отдельно для каждого SKU</span>
                              </div>

                              <section className={styles.comparisonTableWrap}>
                                {loadingComparison ? (
                                  <div className={styles.empty}>Загружаем показатели…</div>
                                ) : (
                                  <div className={styles.tableScroller}>
                                    <table>
                                      <thead>
                                        <tr>
                                          <th className={styles.selectCell}>График</th>
                                          <th className={styles.productColumn}>{header('Товар', 'nm_id')}</th>
                                          <th className={styles.stockMetricColumn}>FBO</th>
                                          <th className={styles.stockMetricColumn}>FBS</th>
                                          <th className={styles.priceMetricColumn}>{header('Цена', 'price')}</th>
                                          <th>{header('СПП', 'spp')}</th>
                                          <th>{header('Показы', 'impressions')}</th>
                                          <th>{header('CTR', 'ctr')}</th>
                                          <th>{header('Открытия', 'opens')}</th>
                                          <th>{header('Корзины', 'carts')}</th>
                                          <th>Корзина / открытия</th>
                                          <th>{header('Заказы', 'orders')}</th>
                                          <th>{header('Выручка', 'revenue')}</th>
                                        </tr>
                                      </thead>
                                      <tbody>
                                        {sortedMembers.map((member) => {
                                          const checked = selectedNmIds.includes(member.nm_id)
                                          return (
                                            <tr key={member.nm_id} className={checked ? styles.selectedRow : ''}>
                                              <td className={styles.selectCell}>
                                                <input
                                                  type="checkbox"
                                                  checked={checked}
                                                  disabled={!checked && selectedNmIds.length >= 5}
                                                  onChange={() => toggleMember(member.nm_id)}
                                                  aria-label={`Показать ${member.nm_id} на графиках`}
                                                />
                                              </td>
                                              <td className={styles.productColumn}>
                                                <div className={styles.productCell}>
                                                  {member.image_url ? (
                                                    // eslint-disable-next-line @next/next/no-img-element
                                                    <img src={member.image_url} alt="" />
                                                  ) : (
                                                    <span className={styles.imagePlaceholder}>WB</span>
                                                  )}
                                                  <div>
                                                    <a
                                                      href={`https://www.wildberries.ru/catalog/${member.nm_id}/detail.aspx`}
                                                      target="_blank"
                                                      rel="noreferrer"
                                                    >
                                                      {member.title || `Товар ${member.nm_id}`}
                                                    </a>
                                                    <small>
                                                      {member.vendor_code || 'Без артикула'} · nmID {member.nm_id}
                                                    </small>
                                                  </div>
                                                </div>
                                              </td>
                                              <td className={styles.stockMetricColumn}>
                                                {formatInt(member.stock.fbo)}
                                              </td>
                                              <td className={styles.stockMetricColumn}>
                                                {formatInt(member.stock.fbs)}
                                              </td>
                                              <td className={styles.priceMetricColumn}>
                                                {formatMoney(member.price.last)}
                                              </td>
                                              <td>{member.spp.last == null ? '—' : `${member.spp.last}%`}</td>
                                              <td>{formatInt(member.funnel.impressions)}</td>
                                              <td>{formatPct(member.funnel.ctr_percent)}</td>
                                              <td>{formatInt(member.funnel.opens)}</td>
                                              <td>{formatInt(member.funnel.carts)}</td>
                                              <td>{formatPct(member.funnel.cart_rate_percent)}</td>
                                              <td className={styles.strongNumber}>
                                                {formatInt(member.funnel.orders)}
                                              </td>
                                              <td className={styles.strongNumber}>
                                                {formatMoney(member.funnel.revenue)}
                                              </td>
                                            </tr>
                                          )
                                        })}
                                      </tbody>
                                    </table>
                                  </div>
                                )}
                              </section>

                              {selectedNmIds.length > 0 ? (
                                <section className={styles.chartsGrid}>
                                  <ComparisonChart metric="price" series={series} />
                                  <ComparisonChart metric="spp_percent" series={series} />
                                  <ComparisonChart metric="impressions" series={series} />
                                  <ComparisonChart metric="ctr_percent" series={series} />
                                  <ComparisonChart metric="orders" series={series} />
                                  <ComparisonChart metric="revenue" series={series} />
                                </section>
                              ) : (
                                <div className={styles.empty}>Выберите товары в таблице для сравнения на графиках.</div>
                              )}
                            </div>
                          </td>
                        </tr>
                      ) : null}
                    </Fragment>
                  )
                })}
                </tbody>
              </table>
            </div>
            <footer className={styles.pagination}>
              <span>
                {formatInt(groupsRangeStart)}–{formatInt(groupsRangeEnd)} из {formatInt(groupsTotal)}
              </span>
              <div>
                <button
                  type="button"
                  disabled={groupsPage <= 1 || loadingGroups}
                  onClick={() => changeGroupsPage(groupsPage - 1)}
                >
                  Назад
                </button>
                <span>
                  Страница {groupsPage} из {groupsTotalPages}
                </span>
                <button
                  type="button"
                  disabled={groupsPage >= groupsTotalPages || loadingGroups}
                  onClick={() => changeGroupsPage(groupsPage + 1)}
                >
                  Далее
                </button>
              </div>
            </footer>
          </>
        )}
      </section>
    </main>
  )
}
