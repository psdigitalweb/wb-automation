import type {
  WBCatalogActivity,
  WBCatalogOrder,
  WBCatalogSort,
} from '@/lib/wbCatalogApi'
import styles from '../catalog.module.css'

export interface CatalogFilterValues {
  q: string
  periodFrom: string
  periodTo: string
  activity: WBCatalogActivity
  sort: WBCatalogSort
  order: WBCatalogOrder
}

type Props = {
  values: CatalogFilterValues
  loading: boolean
  onChange: (values: CatalogFilterValues) => void
  onActivityChange: (activity: WBCatalogActivity) => void
  onApply: () => void
  minDate?: string | null
  maxDate?: string | null
}

const sortOptions: Array<{
  value: `${WBCatalogSort}:${WBCatalogOrder}`
  label: string
}> = [
  { value: 'order_sum:desc', label: 'Сумма заказов — сначала больше' },
  { value: 'orders:desc', label: 'Заказы — сначала больше' },
  { value: 'buyouts:desc', label: 'Выкупы — сначала больше' },
  { value: 'impressions:desc', label: 'Показы — сначала больше' },
  { value: 'ctr:desc', label: 'CTR — сначала больше' },
  { value: 'rating:desc', label: 'Рейтинг — сначала выше' },
  { value: 'price:desc', label: 'Цена — сначала выше' },
  { value: 'title:asc', label: 'Название — А–Я' },
  { value: 'vendor_code:asc', label: 'Артикул — А–Я' },
]

export function CatalogFilters({
  values,
  loading,
  onChange,
  onActivityChange,
  onApply,
  minDate,
  maxDate,
}: Props) {
  const sortValue = `${values.sort}:${values.order}` as const

  return (
    <form
      className={styles.filters}
      onSubmit={(event) => {
        event.preventDefault()
        onApply()
      }}
    >
      <label className={styles.searchField}>
        <span>Поиск</span>
        <input
          type="search"
          value={values.q}
          placeholder="Название, артикул или nmId"
          onChange={(event) => onChange({ ...values, q: event.target.value })}
        />
      </label>

      <label>
        <span>Период с</span>
        <input
          type="date"
          value={values.periodFrom}
          min={minDate ?? undefined}
          max={values.periodTo || maxDate || undefined}
          onChange={(event) =>
            onChange({ ...values, periodFrom: event.target.value })
          }
        />
      </label>

      <label>
        <span>Период по</span>
        <input
          type="date"
          value={values.periodTo}
          min={values.periodFrom || minDate || undefined}
          max={maxDate ?? undefined}
          onChange={(event) =>
            onChange({ ...values, periodTo: event.target.value })
          }
        />
      </label>

      <label>
        <span>Товары</span>
        <select
          value={values.activity}
          onChange={(event) =>
            onActivityChange(event.target.value as WBCatalogActivity)
          }
        >
          <option value="active">Активные</option>
          <option value="all">Все товары</option>
        </select>
      </label>

      <label className={styles.sortField}>
        <span>Сортировка</span>
        <select
          value={sortValue}
          onChange={(event) => {
            const [sort, order] = event.target.value.split(':') as [
              WBCatalogSort,
              WBCatalogOrder,
            ]
            onChange({ ...values, sort, order })
          }}
        >
          {sortOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <button type="submit" disabled={loading}>
        {loading ? 'Обновляем…' : 'Показать'}
      </button>
    </form>
  )
}
