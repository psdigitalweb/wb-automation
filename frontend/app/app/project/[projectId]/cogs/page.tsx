'use client'

import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { apiGetData, apiPut, apiDelete } from '../../../../../lib/apiClient'
import type { ApiError } from '../../../../../lib/apiClient'
import { usePageTitle } from '../../../../../hooks/usePageTitle'
import s from './cogs.module.css'

const SENTINEL_ALL = '__ALL__'

/* UI atoms – unified height 40px, padding 8px 12px, radius 6px, font 14px */

function Field({
  label,
  children,
  className,
}: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <label className={[s.field, className].filter(Boolean).join(' ')}>
      <span className={s.fieldLabel}>{label}</span>
      {children}
    </label>
  )
}

function InputBase({
  type = 'text',
  value,
  onChange,
  placeholder,
  disabled,
  required,
  min,
  max,
  step,
  className,
}: {
  type?: 'text' | 'number'
  value: string
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void
  placeholder?: string
  disabled?: boolean
  required?: boolean
  min?: number
  max?: number
  step?: string
  className?: string
}) {
  const cn = type === 'number' ? s.inputNumber : s.inputText
  return (
    <input
      type={type}
      value={value}
      onChange={onChange}
      placeholder={placeholder}
      disabled={disabled}
      required={required}
      min={min}
      max={max}
      step={step}
      className={[cn, className].filter(Boolean).join(' ')}
    />
  )
}

function InputDate({
  value,
  onChange,
  disabled,
  required,
  className,
}: {
  value: string
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void
  disabled?: boolean
  required?: boolean
  className?: string
}) {
  return (
    <input
      type="date"
      value={value}
      onChange={onChange}
      disabled={disabled}
      required={required}
      className={[s.inputDate, className].filter(Boolean).join(' ')}
    />
  )
}

function SelectBase({
  value,
  onChange,
  disabled,
  children,
  className,
}: {
  value: string
  onChange: (e: React.ChangeEvent<HTMLSelectElement>) => void
  disabled?: boolean
  children: React.ReactNode
  className?: string
}) {
  return (
    <select
      value={value}
      onChange={onChange}
      disabled={disabled}
      className={[s.select, className].filter(Boolean).join(' ')}
    >
      {children}
    </select>
  )
}

function ButtonBase({
  type = 'button',
  onClick,
  disabled,
  children,
  variant = 'primary',
  className,
}: {
  type?: 'button' | 'submit'
  onClick?: () => void
  disabled?: boolean
  children: React.ReactNode
  variant?: 'primary' | 'secondary'
  className?: string
}) {
  const cn = variant === 'secondary' ? s.buttonSecondary : s.button
  return (
    <button type={type} onClick={onClick} disabled={disabled} className={[cn, className].filter(Boolean).join(' ')}>
      {children}
    </button>
  )
}

interface PriceSourceStats {
  total_skus?: number
  with_price?: number
  coverage_pct?: number
  last_snapshot_imported_at?: string | null
  rows?: number
  last_at?: string | null
}

interface PriceSource {
  code: string
  title: string
  description: string
  available: boolean
  stats: PriceSourceStats
}

interface CogsCoverage {
  internal_data_available: boolean
  internal_skus_total: number
  covered_total: number
  missing_total: number
  coverage_pct: number
}

interface CogsRule {
  id: number
  project_id: number
  internal_sku: string
  valid_from: string
  valid_to: string | null
  applies_to: 'sku' | 'all'
  mode: string
  value: number
  currency: string | null
  price_source_code: string | null
  meta_json: Record<string, unknown>
  created_at: string
  updated_at: string
}

interface CogsListResponse {
  items: CogsRule[]
  limit: number
  offset: number
  total: number
}

function todayISO(): string {
  const d = new Date()
  return d.toISOString().slice(0, 10)
}

export default function CogsPage() {
  const params = useParams()
  const projectId = params.projectId as string
  usePageTitle('Себестоимость товаров', projectId)

  const [availableSources, setAvailableSources] = useState<PriceSource[]>([])
  const [sourcesLoading, setSourcesLoading] = useState(true)
  const [coverage, setCoverage] = useState<CogsCoverage | null>(null)
  const [coverageLoading, setCoverageLoading] = useState(true)
  const [asOfDate, setAsOfDate] = useState(todayISO())
  const [rules, setRules] = useState<CogsRule[]>([])
  const [rulesLoading, setRulesLoading] = useState(true)
  const [total, setTotal] = useState(0)
  const [limit] = useState(50)
  const [offset, setOffset] = useState(0)
  const [search, setSearch] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'add' | 'bulk'>('add')

  const [formAppliesTo, setFormAppliesTo] = useState<'sku' | 'all'>('sku')
  const [formSku, setFormSku] = useState('')
  const [formValidFrom, setFormValidFrom] = useState(todayISO())
  const [formValidTo, setFormValidTo] = useState('')
  const [formMode, setFormMode] = useState<'fixed' | 'percent_of_price'>('fixed')
  const [formPriceSource, setFormPriceSource] = useState('')
  const [formValue, setFormValue] = useState('')
  const [formCurrency, setFormCurrency] = useState('RUB')
  const [submitting, setSubmitting] = useState(false)
  const [toast, setToast] = useState<string | null>(null)

  const [bulkDefaults, setBulkDefaults] = useState({
    valid_from: todayISO(),
    valid_to: '',
    mode: 'percent_of_price' as 'fixed' | 'percent_of_price',
    currency: 'RUB',
    price_source_code: '',
  })
  const [bulkText, setBulkText] = useState('')
  const [bulkSaveResult, setBulkSaveResult] = useState<{
    inserted: number
    updated: number
    failed: number
    errors: Array<{ row_index: number; message: string; internal_sku?: string }>
  } | null>(null)
  const [fillMissingLoading, setFillMissingLoading] = useState(false)

  const loadPriceSources = useCallback(async () => {
    try {
      setSourcesLoading(true)
      const data = await apiGetData<{ available_sources: PriceSource[] }>(
        `/api/v1/projects/${projectId}/cogs/price-sources`
      )
      setAvailableSources(data.available_sources || [])
    } catch (e) {
      console.error('Failed to load price sources:', e)
      setAvailableSources([])
    } finally {
      setSourcesLoading(false)
    }
  }, [projectId])

  const loadCoverage = useCallback(async () => {
    try {
      setCoverageLoading(true)
      const q = new URLSearchParams()
      if (asOfDate) q.set('as_of_date', asOfDate)
      const data = await apiGetData<CogsCoverage>(
        `/api/v1/projects/${projectId}/cogs/coverage?${q.toString()}`
      )
      setCoverage(data)
    } catch (e) {
      console.error('Failed to load coverage:', e)
      setCoverage(null)
    } finally {
      setCoverageLoading(false)
    }
  }, [projectId, asOfDate])

  const loadRules = useCallback(async () => {
    try {
      setRulesLoading(true)
      const q = new URLSearchParams()
      q.set('limit', String(limit))
      q.set('offset', String(offset))
      if (search.trim()) q.set('search', search.trim())
      const data = await apiGetData<CogsListResponse>(
        `/api/v1/projects/${projectId}/cogs/direct-rules?${q.toString()}`
      )
      setRules(data.items)
      setTotal(data.total)
    } catch (e) {
      console.error('Failed to load rules:', e)
      setRules([])
      setTotal(0)
    } finally {
      setRulesLoading(false)
    }
  }, [projectId, limit, offset, search])

  useEffect(() => {
    setCoverage(null)
    setCoverageLoading(true)
    setRules([])
    setRulesLoading(true)
    setAvailableSources([])
    setSourcesLoading(true)
  }, [projectId])

  useEffect(() => {
    loadPriceSources()
  }, [loadPriceSources])

  useEffect(() => {
    loadCoverage()
  }, [loadCoverage])

  useEffect(() => {
    setOffset(0)
  }, [search])

  useEffect(() => {
    loadRules()
  }, [loadRules])

  const availableForPercent = availableSources.filter((s) => s.available)
  const noSourcesForPercent = formMode === 'percent_of_price' && availableForPercent.length === 0

  const handleAddRule = async (e: React.FormEvent) => {
    e.preventDefault()
    const sku = formAppliesTo === 'all' ? SENTINEL_ALL : formSku.trim()
    if (formAppliesTo === 'sku' && !formSku.trim()) {
      setError('Укажите артикул для правила «Один артикул»')
      return
    }
    if (!formValidFrom || !formValue) {
      setError('Обязательны «Действует с» и «Значение»')
      return
    }
    if (formMode === 'percent_of_price') {
      const v = parseFloat(formValue)
      if (v < 0 || v > 100) {
        setError('Процент должен быть от 0 до 100')
        return
      }
      if (!formPriceSource) {
        setError('Выберите источник цены для режима «% от цены»')
        return
      }
    }
    setError(null)
    setSubmitting(true)
    try {
      await apiPut(`/api/v1/projects/${projectId}/cogs/direct-rules:bulk-upsert`, {
        items: [
          {
            internal_sku: sku,
            valid_from: formValidFrom,
            valid_to: formValidTo || null,
            applies_to: formAppliesTo,
            mode: formMode,
            value: parseFloat(formValue),
            currency: formMode === 'fixed' ? formCurrency : null,
            price_source_code: formMode === 'percent_of_price' ? formPriceSource : null,
            meta_json: {},
          },
        ],
      })
      setToast('Правило добавлено')
      setFormSku('')
      setFormValidFrom(todayISO())
      setFormValidTo('')
      setFormValue('')
      setFormPriceSource('')
      setTimeout(() => setToast(null), 3000)
      setSearch('')
      setOffset(0)
      loadCoverage()
      loadRules()
    } catch (err: unknown) {
      const apiErr = err as ApiError
      setError(apiErr?.detail || 'Не удалось добавить правило')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (ruleId: number) => {
    if (!confirm('Удалить это правило?')) return
    try {
      await apiDelete(`/api/v1/projects/${projectId}/cogs/direct-rules/${ruleId}`)
      loadCoverage()
      loadRules()
    } catch (e) {
      console.error('Delete failed:', e)
      setError((e as ApiError)?.detail || 'Ошибка удаления')
    }
  }

  const handleFillMissing = async () => {
    if (!coverage?.internal_data_available) return
    setFillMissingLoading(true)
    setBulkSaveResult(null)
    try {
      const q = new URLSearchParams()
      q.set('limit', '200')
      if (asOfDate) q.set('as_of_date', asOfDate)
      const data = await apiGetData<{ internal_data_available: boolean; total: number; items: Array<{ internal_sku: string }> }>(
        `/api/v1/projects/${projectId}/cogs/missing-skus?${q.toString()}`
      )
      const lines = data.items.map((it) => `${it.internal_sku}\t`)
      setBulkText(lines.join('\n'))
      setActiveTab('bulk')
      if (lines.length === 0) setToast('Нет недостающих артикулов')
      else setToast(`Подставлено ${lines.length} недостающих артикулов`)
      setTimeout(() => setToast(null), 3000)
    } catch (e) {
      console.error('Fill missing failed:', e)
      setError((e as ApiError)?.detail || 'Ошибка «Заполнить недостающие»')
    } finally {
      setFillMissingLoading(false)
    }
  }

  const parseBulk = (): Array<{ internal_sku: string; value: string; valid_from: string; valid_to: string }> => {
    const lines = bulkText.trim().split(/\r?\n/).filter(Boolean)
    const out: Array<{ internal_sku: string; value: string; valid_from: string; valid_to: string }> = []
    for (const line of lines) {
      const cells = line.split('\t')
      const internal_sku = (cells[0] || '').trim()
      if (!internal_sku) continue
      const value = (cells[1] ?? '').trim()
      out.push({
        internal_sku,
        value,
        valid_from: (cells[2] ?? '').trim() || bulkDefaults.valid_from,
        valid_to: (cells[3] ?? '').trim() || bulkDefaults.valid_to,
      })
    }
    return out
  }

  const handleBulkSave = async () => {
    const all = parseBulk()
    const rows = all.filter((r) => r.value !== '')
    const skipped = all.length - rows.length
    if (!rows.length) {
      setError('Вставьте хотя бы одну строку с значением: артикул TAB значение')
      return
    }
    setError(null)
    setBulkSaveResult(null)
    setSubmitting(true)
    try {
      const defaultSource = bulkDefaults.mode === 'percent_of_price' ? (bulkDefaults.price_source_code || availableForPercent[0]?.code) : null
      const items = rows.map((r) => {
        const val = parseFloat(r.value)
        if (Number.isNaN(val) || val < 0) {
          throw new Error(`Неверное значение для ${r.internal_sku}: ${r.value}`)
        }
        return {
          internal_sku: r.internal_sku,
          valid_from: r.valid_from || bulkDefaults.valid_from,
          valid_to: r.valid_to || null,
          applies_to: 'sku' as const,
          mode: bulkDefaults.mode,
          value: val,
          currency: bulkDefaults.mode === 'fixed' ? bulkDefaults.currency : null,
          price_source_code: bulkDefaults.mode === 'percent_of_price' ? defaultSource : null,
          meta_json: {},
        }
      })
      const { data: res } = await apiPut<{ inserted: number; updated: number; failed: number; errors: Array<{ row_index: number; message: string; internal_sku?: string }> }>(
        `/api/v1/projects/${projectId}/cogs/direct-rules:bulk-upsert`,
        { items }
      )
      setBulkSaveResult({
        inserted: res.inserted ?? 0,
        updated: res.updated ?? 0,
        failed: res.failed ?? 0,
        errors: res.errors ?? [],
      })
      setToast(
        `Добавлено: ${res.inserted ?? 0}, Обновлено: ${res.updated ?? 0}, Ошибок: ${res.failed ?? 0}` +
        (skipped ? ` (пропущено ${skipped} строк без значения)` : '')
      )
      setTimeout(() => setToast(null), 4000)
      loadCoverage()
      loadRules()
    } catch (err: unknown) {
      const apiErr = err as ApiError
      setError(apiErr?.detail || 'Ошибка массового сохранения')
    } finally {
      setSubmitting(false)
    }
  }

  const sourceByCode: Record<string, string> = {}
  availableSources.forEach((src) => { sourceByCode[src.code] = src.title })

  return (
    <div className={[s.root, 'container'].join(' ')}>
      <h1>Настройки себестоимости</h1>
      <Link href={`/app/project/${projectId}/settings`} className={s.linkAsButton}>
        ← Назад к настройкам
      </Link>

      {toast && (
        <div style={{ padding: '10px', marginTop: '10px', backgroundColor: '#d4edda', borderRadius: 6 }}>
          {toast}
        </div>
      )}
      {error && (
        <div style={{ padding: '10px', marginTop: '10px', backgroundColor: '#f8d7da', borderRadius: 6 }}>
          {error}
        </div>
      )}

      <div className="card" style={{ marginTop: 24 }}>
        <h2>Покрытие</h2>
        <div className={s.gridCoverage}>
          <div className={s.gridCoverageItem}>
            <span className={s.fieldLabel}>На дату:</span>
            <InputDate value={asOfDate} onChange={(e) => setAsOfDate(e.target.value)} />
          </div>
          <ButtonBase onClick={loadCoverage} disabled={coverageLoading}>
            Показать
          </ButtonBase>
          {coverage?.internal_data_available && (
            <ButtonBase
              onClick={handleFillMissing}
              disabled={fillMissingLoading || coverage.coverage_pct >= 100}
            >
              {fillMissingLoading ? 'Загрузка…' : 'Заполнить недостающие'}
            </ButtonBase>
          )}
        </div>
        {coverageLoading ? (
          <p>Загрузка…</p>
        ) : !coverage?.internal_data_available ? (
          <p>Нет internal data. Сначала синхронизируйте Internal Data.</p>
        ) : coverage ? (
          <p>
            Артикулы: <strong>{coverage.internal_skus_total}</strong> · С покрытием:{' '}
            <strong>{coverage.covered_total}</strong> · Недостающие: <strong>{coverage.missing_total}</strong> · Покрытие:{' '}
            <strong>{coverage.coverage_pct.toFixed(1)}%</strong>
          </p>
        ) : (
          <p>Нет данных по покрытию</p>
        )}
      </div>

      <div className={s.gridTabs}>
        <button
          type="button"
          onClick={() => setActiveTab('add')}
          className={[s.tab, activeTab === 'add' && s.tabActive].filter(Boolean).join(' ')}
        >
          Добавить правило
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('bulk')}
          className={[s.tab, activeTab === 'bulk' && s.tabActive].filter(Boolean).join(' ')}
        >
          Массовое заполнение
        </button>
      </div>

      {activeTab === 'add' && (
        <div className="card" style={{ marginTop: 16 }}>
          <h2>Добавить правило</h2>
          {noSourcesForPercent && (
            <div style={{ padding: 12, marginBottom: 12, backgroundColor: '#fff3cd', borderRadius: 6 }}>
              В проекте нет доступных источников цены. Подключите Internal Data или загрузите WB admin prices.
            </div>
          )}
          <form onSubmit={handleAddRule}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 12 }}>
              <div className={s.gridFormRow1}>
                <Field label="Применить к">
                  <SelectBase value={formAppliesTo} onChange={(e) => setFormAppliesTo(e.target.value as 'sku' | 'all')}>
                    <option value="sku">Один артикул</option>
                    <option value="all">Все артикулы</option>
                  </SelectBase>
                </Field>
                <Field label="Артикул">
                  <InputBase
                    type="text"
                    value={formSku}
                    onChange={(e) => setFormSku(e.target.value)}
                    placeholder="—"
                    disabled={formAppliesTo === 'all'}
                  />
                </Field>
                <Field label="Действует с">
                  <InputDate value={formValidFrom} onChange={(e) => setFormValidFrom(e.target.value)} required />
                </Field>
                <Field label="По">
                  <InputDate value={formValidTo} onChange={(e) => setFormValidTo(e.target.value)} />
                </Field>
                <Field label="Тип">
                  <SelectBase value={formMode} onChange={(e) => setFormMode(e.target.value as 'fixed' | 'percent_of_price')}>
                    <option value="fixed">Фиксированная сумма</option>
                    <option value="percent_of_price">% от цены</option>
                  </SelectBase>
                </Field>
                <Field label="Источник цены">
                  <SelectBase
                    value={formPriceSource}
                    onChange={(e) => setFormPriceSource(e.target.value)}
                    disabled={formMode === 'fixed' || availableForPercent.length === 0}
                  >
                    <option value="">—</option>
                    {availableForPercent.map((src) => (
                      <option key={src.code} value={src.code}>
                        {src.title}
                      </option>
                    ))}
                  </SelectBase>
                </Field>
              </div>
              <div className={s.gridFormRow2}>
                <Field label="Значение">
                  <InputBase
                    type="number"
                    value={formValue}
                    onChange={(e) => setFormValue(e.target.value)}
                    placeholder={formMode === 'percent_of_price' ? '0–100%' : 'Напр. 40'}
                    required
                    min={formMode === 'percent_of_price' ? 0 : undefined}
                    max={formMode === 'percent_of_price' ? 100 : undefined}
                    step="any"
                  />
                </Field>
                {formMode === 'fixed' ? (
                  <Field label="Валюта">
                    <InputBase type="text" value={formCurrency} onChange={(e) => setFormCurrency(e.target.value)} />
                  </Field>
                ) : (
                  <div className={s.gridFormSpacer} />
                )}
                <div style={{ display: 'flex', alignItems: 'flex-end' }}>
                  <ButtonBase
                    type="submit"
                    disabled={
                      submitting ||
                      noSourcesForPercent ||
                      (formMode === 'percent_of_price' && !formPriceSource)
                    }
                  >
                    {submitting ? 'Добавляем…' : 'Добавить'}
                  </ButtonBase>
                </div>
              </div>
            </div>
          </form>
        </div>
      )}

      {activeTab === 'bulk' && (
        <div className="card" style={{ marginTop: 16 }}>
          <h2>Массовое заполнение</h2>
          <p style={{ fontSize: '0.9rem', color: '#666', marginBottom: 12 }}>
            Вставьте TSV (например из Excel): артикул TAB значение. Опционально: TAB действует с, TAB по.
          </p>
          <div className={s.gridBulk}>
            <div className={s.gridBulkItem}>
              <span className={s.fieldLabel}>Действует с</span>
              <InputDate
                value={bulkDefaults.valid_from}
                onChange={(e) => setBulkDefaults((d) => ({ ...d, valid_from: e.target.value }))}
              />
            </div>
            <div className={s.gridBulkItem}>
              <span className={s.fieldLabel}>По</span>
              <InputDate
                value={bulkDefaults.valid_to}
                onChange={(e) => setBulkDefaults((d) => ({ ...d, valid_to: e.target.value }))}
              />
            </div>
            <div className={s.gridBulkItem}>
              <span className={s.fieldLabel}>Тип</span>
              <SelectBase
                value={bulkDefaults.mode}
                onChange={(e) => setBulkDefaults((d) => ({ ...d, mode: e.target.value as 'fixed' | 'percent_of_price' }))}
              >
                <option value="fixed">Фиксированная</option>
                <option value="percent_of_price">% от цены</option>
              </SelectBase>
            </div>
            {bulkDefaults.mode === 'percent_of_price' && (
              <div className={s.gridBulkItem}>
                <span className={s.fieldLabel}>Источник цены</span>
                <SelectBase
                  value={bulkDefaults.price_source_code}
                  onChange={(e) => setBulkDefaults((d) => ({ ...d, price_source_code: e.target.value }))}
                >
                  <option value="">—</option>
                  {availableForPercent.map((src) => (
                    <option key={src.code} value={src.code}>{src.title}</option>
                  ))}
                </SelectBase>
              </div>
            )}
            {bulkDefaults.mode === 'fixed' && (
              <div className={s.gridBulkItem}>
                <span className={s.fieldLabel}>Валюта</span>
                <InputBase
                  type="text"
                  value={bulkDefaults.currency}
                  onChange={(e) => setBulkDefaults((d) => ({ ...d, currency: e.target.value }))}
                />
              </div>
            )}
          </div>
          <textarea
            value={bulkText}
            onChange={(e) => setBulkText(e.target.value)}
            placeholder={'Артикул-1\t100\nАртикул-2\t200'}
            className={s.textarea}
          />
          <div style={{ marginTop: 12 }}>
            <ButtonBase onClick={handleBulkSave} disabled={submitting || !bulkText.trim()}>
              {submitting ? 'Сохранение…' : 'Сохранить'}
            </ButtonBase>
          </div>
          {bulkSaveResult && (
            <div style={{ marginTop: 12, fontSize: '0.9rem' }}>
              <p>Добавлено: {bulkSaveResult.inserted} · Обновлено: {bulkSaveResult.updated} · Ошибок: {bulkSaveResult.failed}</p>
              {bulkSaveResult.errors.length > 0 && (
                <ul style={{ color: 'crimson' }}>
                  {bulkSaveResult.errors.slice(0, 10).map((e, i) => (
                    <li key={i}>Строка {e.row_index}: {e.message} {e.internal_sku ? `(${e.internal_sku})` : ''}</li>
                  ))}
                  {bulkSaveResult.errors.length > 10 && <li>… и ещё {bulkSaveResult.errors.length - 10}</li>}
                </ul>
              )}
            </div>
          )}
        </div>
      )}

      <div className="card" style={{ marginTop: 24 }}>
        <h2>Правила</h2>
        <div className={s.searchWrap}>
          <InputBase
            type="text"
            placeholder="Поиск по артикулу"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        {rulesLoading ? (
          <p>Загрузка…</p>
        ) : (
          <>
            <table>
              <thead>
                <tr>
                  <th>Применение</th>
                  <th>Артикул</th>
                  <th>Действует с</th>
                  <th>По</th>
                  <th>Тип</th>
                  <th>Источник цены</th>
                  <th>Значение</th>
                  <th>Валюта</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {rules.length === 0 ? (
                  <tr>
                    <td colSpan={9} style={{ textAlign: 'center' }}>
                      Правил нет
                    </td>
                  </tr>
                ) : (
                  rules.map((r) => (
                    <tr key={r.id}>
                      <td>{r.applies_to === 'all' ? 'По умолчанию' : 'Артикул'}</td>
                      <td>{r.internal_sku === SENTINEL_ALL ? 'Все артикулы (по умолчанию)' : r.internal_sku}</td>
                      <td>{r.valid_from}</td>
                      <td>{r.valid_to ?? '—'}</td>
                      <td>{r.mode === 'percent_of_price' ? '% от цены' : r.mode === 'fixed' ? 'Фиксированная сумма' : r.mode}</td>
                      <td>{r.price_source_code ? (sourceByCode[r.price_source_code] ?? r.price_source_code) : '—'}</td>
                      <td>{r.mode === 'percent_of_price' ? `${Math.round(r.value)}%` : r.value}</td>
                      <td>{r.currency ?? '—'}</td>
                      <td className={s.tableDeleteCell}>
                        <button
                          type="button"
                          className={s.tableDeleteBtn}
                          onClick={() => handleDelete(r.id)}
                        >
                          Удалить
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
            <div className={s.paginationWrap}>
              <button
                type="button"
                className={s.paginationBtn}
                onClick={() => setOffset(Math.max(0, offset - limit))}
                disabled={offset === 0}
              >
                Назад
              </button>
              <span style={{ margin: '0 12px' }}>
                {Math.floor(offset / limit) + 1} (всего: {total})
              </span>
              <button
                type="button"
                className={s.paginationBtn}
                onClick={() => setOffset(offset + limit)}
                disabled={rules.length < limit || offset + limit >= total}
              >
                Вперёд
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
