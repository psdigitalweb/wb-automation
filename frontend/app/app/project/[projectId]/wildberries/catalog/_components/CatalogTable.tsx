import Link from 'next/link'
import { useState } from 'react'
import type { WBCatalogItem } from '@/lib/wbCatalogApi'
import styles from '../catalog.module.css'

const integerFormatter = new Intl.NumberFormat('ru-RU', {
  maximumFractionDigits: 0,
})

const moneyFormatter = new Intl.NumberFormat('ru-RU', {
  style: 'currency',
  currency: 'RUB',
  maximumFractionDigits: 0,
})

function formatInteger(value: number | null | undefined) {
  return integerFormatter.format(value ?? 0)
}

function formatMoney(value: number | null | undefined) {
  return value == null ? '—' : moneyFormatter.format(value)
}

function formatRatio(value: number | null | undefined) {
  return value == null ? '—' : `${(value * 100).toFixed(1)}%`
}

function formatPercentPoints(value: number | null | undefined) {
  return value == null ? '—' : `${value.toFixed(1)}%`
}

function ProductPhoto({ item }: { item: WBCatalogItem }) {
  const [failed, setFailed] = useState(false)
  if (!item.main_photo_url || failed) {
    return <div className={styles.photoPlaceholder}>Нет фото</div>
  }
  return (
    <img
      className={styles.photo}
      src={item.main_photo_url}
      alt=""
      loading="lazy"
      onError={() => setFailed(true)}
    />
  )
}

export function CatalogTable({
  items,
  projectId,
}: {
  items: WBCatalogItem[]
  projectId: string
}) {
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <colgroup>
          <col className={styles.photoColumn} />
          <col className={styles.productColumn} />
          <col className={styles.priceColumn} />
          <col className={styles.reachColumn} />
          <col className={styles.funnelColumn} />
          <col className={styles.resultColumn} />
        </colgroup>
        <thead>
          <tr>
            <th>Фото</th>
            <th>Товар</th>
            <th>Цена и отзывы</th>
            <th>Охват</th>
            <th>Воронка</th>
            <th>Результат</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.nm_id}>
              <td className={styles.photoCell}>
                <ProductPhoto item={item} />
              </td>
              <td>
                <div
                  className={`${styles.cellLines} ${styles.productLines}`}
                >
                  <Link
                    className={styles.productTitle}
                    href={`/app/project/${projectId}/wildberries/catalog/${item.nm_id}`}
                    title={item.title ?? ''}
                  >
                    {item.title || 'Без названия'}
                  </Link>
                  <div className={styles.secondaryLine}>
                    <span title={item.vendor_code ?? ''}>
                      {item.vendor_code || 'Без артикула'}
                    </span>
                    <span className={styles.separator}>·</span>
                    <span className={styles.rating}>
                      {item.rating == null ? '★ —' : `★ ${item.rating.toFixed(1)}`}
                    </span>
                  </div>
                  <div className={styles.secondaryLine}>
                    <a
                      href={`https://www.wildberries.ru/catalog/${item.nm_id}/detail.aspx`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {item.nm_id}
                    </a>
                    <span className={styles.separator}>·</span>
                    <span
                      className={`${styles.activityDot} ${
                        item.is_active ? styles.activityDotActive : ''
                      }`}
                      title={item.is_active ? 'Активен на WB' : 'Не подтверждён как активный'}
                      aria-label={item.is_active ? 'Активен на WB' : 'Не подтверждён как активный'}
                    />
                  </div>
                </div>
              </td>
              <td>
                <div className={styles.cellLines}>
                  <div className={styles.primaryMetric}>
                    {formatMoney(item.showcase_price)}
                    {item.spp_percent != null && (
                      <span className={styles.inlineHint}>
                        СПП {formatPercentPoints(item.spp_percent)}
                      </span>
                    )}
                  </div>
                  <div className={styles.secondaryLine}>
                    {item.rrp_price == null ? '\u00A0' : `РРЦ ${formatMoney(item.rrp_price)}`}
                  </div>
                  <div className={styles.secondaryLine}>
                    {formatInteger(item.reviews_count)} отзывов
                  </div>
                </div>
              </td>
              <td>
                <div className={styles.cellLines}>
                  <div>
                    <span className={styles.metricLabel}>Показы</span>
                    <strong>{formatInteger(item.impressions)}</strong>
                  </div>
                  <div>
                    <span className={styles.metricLabel}>Переходы</span>
                    <strong>{formatInteger(item.card_clicks)}</strong>
                  </div>
                  <div>
                    <span className={styles.metricLabel}>CTR</span>
                    <strong>{formatPercentPoints(item.ctr_percent)}</strong>
                  </div>
                </div>
              </td>
              <td>
                <div className={styles.cellLines}>
                  <div>
                    <span className={styles.metricLabel}>Открытия</span>
                    <strong>{formatInteger(item.opens)}</strong>
                  </div>
                  <div>
                    <span className={styles.metricLabel}>Корзины</span>
                    <strong>{formatInteger(item.cart_count)}</strong>
                    <span className={styles.inlineHint}>
                      {formatRatio(item.cart_rate)}
                    </span>
                  </div>
                  <div>
                    <span className={styles.metricLabel}>Заказы</span>
                    <strong>{formatInteger(item.order_count)}</strong>
                    <span className={styles.inlineHint}>
                      {formatRatio(item.cart_to_order_rate)}
                    </span>
                  </div>
                </div>
              </td>
              <td>
                <div className={styles.cellLines}>
                  <div>
                    <span className={styles.metricLabel}>Заказы</span>
                    <strong>{formatMoney(item.order_sum)}</strong>
                  </div>
                  <div>
                    <span className={styles.metricLabel}>Выкупы</span>
                    <strong>{formatInteger(item.buyout_count)}</strong>
                  </div>
                  <div>
                    <span className={styles.metricLabel}>Сумма</span>
                    <strong>{formatMoney(item.buyout_sum)}</strong>
                  </div>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
