'use client'

import { useState, useEffect } from 'react'
import { useParams, useSearchParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { apiGet, apiPost, apiPut, apiDelete } from '../../../../../lib/apiClient'
import type { ApiError } from '../../../../../lib/apiClient'
import { usePageTitle } from '../../../../../hooks/usePageTitle'
import s from './additional-costs.module.css'

/* UI atoms – unified height 40px, padding 8px 12px, radius 6px, font 14px */

function Field({
  label,
  children,
  className,
}: {
  label: string
  children: React.ReactNode
  className?: string
}) {
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

interface AdditionalCostEntry {
  id: number
  project_id: number
  scope: 'project' | 'marketplace' | 'product'
  marketplace_code: string | null
  period_from: string
  period_to: string
  date_incurred: string | null
  currency: string
  amount: number | string  // Can be string from API (Decimal serialized as string)
  category: string
  subcategory: string | null
  vendor: string | null
  description: string | null
  nm_id: number | null
  internal_sku: string | null
  source: string
  external_uid: string | null
  payload: Record<string, unknown>
  payload_hash: string | null
  created_at: string
  updated_at: string
}

interface AdditionalCostEntriesListResponse {
  items: AdditionalCostEntry[]
  limit: number
  offset: number
}

interface AdditionalCostSummaryBreakdownItem {
  category: string
  subcategory: string | null
  marketplace_code: string | null
  internal_sku: string | null
  nm_id: number | null
  prorated_amount: number | string  // Can be string from API (Decimal serialized as string)
}

interface AdditionalCostSummaryResponse {
  total_amount: number | string  // Can be string from API (Decimal serialized as string)
  breakdown: AdditionalCostSummaryBreakdownItem[]
}

interface WarehouseLaborRate {
  id?: number
  labor_day_id?: number
  rate_name: string
  employees_count: string  // Store as string for input normalization
  rate_amount: string  // Store as string for input normalization
  currency?: string
  _error?: string  // Inline validation error
}

interface WarehouseLaborDay {
  id: number
  project_id: number
  work_date: string
  marketplace_code: string | null
  notes: string | null
  rates: Array<{
    id?: number
    labor_day_id?: number
    rate_name: string
    employees_count: number | string  // Can be number from API or string in form
    rate_amount: number | string  // Can be number from API or string in form
    currency?: string
  }>
  total_amount: string
  created_at: string
  updated_at: string
}

interface WarehouseLaborDaysListResponse {
  items: WarehouseLaborDay[]
}

interface PackagingTariffItem {
  id: number
  project_id: number
  internal_sku: string
  valid_from: string
  cost_per_unit: string | number
  currency: string
  notes: string | null
  created_at: string
  updated_at: string
}

interface PackagingTariffsListResponse {
  items: PackagingTariffItem[]
  total: number
}

interface PackagingSummaryBreakdownItem {
  internal_sku: string
  units_sold: number
  amount: string | number
}

interface PackagingSummaryResponse {
  total_amount: string | number
  breakdown: PackagingSummaryBreakdownItem[]
  missing_tariff: {
    count: number
    skus: string[]
  }
}

interface WarehouseLaborSummaryBreakdownItem {
  work_date?: string | null
  marketplace_code?: string | null
  total_amount: string
}

interface WarehouseLaborSummaryResponse {
  total_amount: string
  breakdown: WarehouseLaborSummaryBreakdownItem[]
}

interface ProjectMarketplace {
  id: number
  marketplace_code: string
  marketplace_name: string
}

interface AdditionalCostCategoryItem {
  name: string
  subcategories: string[]
}

interface AdditionalCostCategoriesResponse {
  categories: AdditionalCostCategoryItem[]
}

export default function AdditionalCostsPage() {
  const params = useParams()
  const projectId = params.projectId as string
  usePageTitle('Управление расходами', projectId)
  const searchParams = useSearchParams()
  const router = useRouter()
  
  // Get active tab from query param, default to 'expenses'
  const tabParam = searchParams.get('tab')
  const activeTab: 'expenses' | 'warehouse' | 'packaging' = 
    tabParam === 'warehouse' ? 'warehouse' : 
    tabParam === 'packaging' ? 'packaging' : 
    'expenses'

  const [entries, setEntries] = useState<AdditionalCostEntry[]>([])
  const [entriesLoading, setEntriesLoading] = useState(true)
  const [limit] = useState(50)
  const [offset, setOffset] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)

  // Filters
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [filterScope, setFilterScope] = useState<string>('')
  const [marketplaceCode, setMarketplaceCode] = useState('')
  const [category, setCategory] = useState('')
  const [nmId, setNmId] = useState('')
  const [filterInternalSku, setFilterInternalSku] = useState('')

  // Summary
  const [summary, setSummary] = useState<AdditionalCostSummaryResponse | null>(null)
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [summaryDateFrom, setSummaryDateFrom] = useState('')
  const [summaryDateTo, setSummaryDateTo] = useState('')
  const [summaryLevel, setSummaryLevel] = useState<'project' | 'marketplace' | 'product'>('project')
  const [summaryMarketplaceCode, setSummaryMarketplaceCode] = useState('')

  // Add form
  const [formScope, setFormScope] = useState<'project' | 'marketplace' | 'product'>('project')
  const [formPeriodFrom, setFormPeriodFrom] = useState('')
  const [formPeriodTo, setFormPeriodTo] = useState('')
  const [formDateIncurred, setFormDateIncurred] = useState('')
  const [formAmount, setFormAmount] = useState('')
  const [formCategory, setFormCategory] = useState('')
  const [formSubcategory, setFormSubcategory] = useState('')
  const [formVendor, setFormVendor] = useState('')
  const [formDescription, setFormDescription] = useState('')
  const [formMarketplaceCode, setFormMarketplaceCode] = useState('')
  const [formNmId, setFormNmId] = useState('')
  const [formInternalSku, setFormInternalSku] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // Edit
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editForm, setEditForm] = useState<Partial<AdditionalCostEntry>>({})

  // Warehouse Labor state
  const [warehouseDays, setWarehouseDays] = useState<WarehouseLaborDay[]>([])
  const [warehouseDaysLoading, setWarehouseDaysLoading] = useState(false)
  const [warehouseDateFrom, setWarehouseDateFrom] = useState('')
  const [warehouseDateTo, setWarehouseDateTo] = useState('')
  const [warehouseMarketplaceCode, setWarehouseMarketplaceCode] = useState('')
  const [warehouseSummary, setWarehouseSummary] = useState<WarehouseLaborSummaryResponse | null>(null)
  const [warehouseSummaryLoading, setWarehouseSummaryLoading] = useState(false)
  const [warehouseSummaryDateFrom, setWarehouseSummaryDateFrom] = useState('')
  const [warehouseSummaryDateTo, setWarehouseSummaryDateTo] = useState('')
  const [warehouseSummaryGroupBy, setWarehouseSummaryGroupBy] = useState<'day' | 'marketplace' | 'project'>('day')
  const [warehouseSummaryMarketplaceCode, setWarehouseSummaryMarketplaceCode] = useState('')
  const [warehouseEditingDayId, setWarehouseEditingDayId] = useState<number | null>(null)
  const [warehouseFormWorkDate, setWarehouseFormWorkDate] = useState('')
  const [warehouseFormMarketplaceCode, setWarehouseFormMarketplaceCode] = useState('')
  const [warehouseFormNotes, setWarehouseFormNotes] = useState('')
  const [warehouseFormRates, setWarehouseFormRates] = useState<WarehouseLaborRate[]>([])
  const [warehouseSubmitting, setWarehouseSubmitting] = useState(false)
  const [projectMarketplaces, setProjectMarketplaces] = useState<ProjectMarketplace[]>([])
  const [categories, setCategories] = useState<AdditionalCostCategoryItem[]>([])

  // Packaging state
  const [packagingSummary, setPackagingSummary] = useState<PackagingSummaryResponse | null>(null)
  const [packagingSummaryLoading, setPackagingSummaryLoading] = useState(false)
  const [packagingSummaryDateFrom, setPackagingSummaryDateFrom] = useState('')
  const [packagingSummaryDateTo, setPackagingSummaryDateTo] = useState('')
  const [packagingSummaryGroupBy, setPackagingSummaryGroupBy] = useState<'project' | 'product'>('project')
  const [packagingTariffs, setPackagingTariffs] = useState<PackagingTariffItem[]>([])
  const [packagingTariffsLoading, setPackagingTariffsLoading] = useState(false)
  const [packagingTariffsQuery, setPackagingTariffsQuery] = useState('')
  const [packagingTariffsOnlyCurrent, setPackagingTariffsOnlyCurrent] = useState(true)
  const [packagingBulkValidFrom, setPackagingBulkValidFrom] = useState('')
  const [packagingBulkCostPerUnit, setPackagingBulkCostPerUnit] = useState('')
  const [packagingBulkNotes, setPackagingBulkNotes] = useState('')
  const [packagingBulkSkuList, setPackagingBulkSkuList] = useState('')
  const [packagingBulkSubmitting, setPackagingBulkSubmitting] = useState(false)
  const [packagingBulkResult, setPackagingBulkResult] = useState<{created: number, updated: number, skipped: number} | null>(null)
  const [packagingExpandedHistory, setPackagingExpandedHistory] = useState<Set<number>>(new Set())

  useEffect(() => {
    setEntries([])
    setEntriesLoading(true)
    // Set default warehouse date range to current month
    const now = new Date()
    const firstDay = new Date(now.getFullYear(), now.getMonth(), 1)
    const lastDay = new Date(now.getFullYear(), now.getMonth() + 1, 0)
    setWarehouseDateFrom(firstDay.toISOString().split('T')[0])
    setWarehouseDateTo(lastDay.toISOString().split('T')[0])
    setWarehouseSummaryDateFrom(firstDay.toISOString().split('T')[0])
    setWarehouseSummaryDateTo(lastDay.toISOString().split('T')[0])
    setPackagingSummaryDateFrom(firstDay.toISOString().split('T')[0])
    setPackagingSummaryDateTo(lastDay.toISOString().split('T')[0])
    loadProjectMarketplaces()
    loadCategories()
    loadPackagingTariffs()
  }, [projectId])

  const loadEntries = async () => {
    try {
      setEntriesLoading(true)
      setError(null)
      const q = new URLSearchParams()
      q.set('limit', String(limit))
      q.set('offset', String(offset))
      if (dateFrom) q.set('date_from', dateFrom)
      if (dateTo) q.set('date_to', dateTo)
      if (filterScope) q.set('scope', filterScope)
      if (marketplaceCode) q.set('marketplace_code', marketplaceCode)
      if (category) q.set('category', category)
      if (nmId) q.set('nm_id', nmId)
      if (filterInternalSku) q.set('internal_sku', filterInternalSku)

      const result = await apiGet<AdditionalCostEntriesListResponse>(
        `/api/v1/projects/${projectId}/additional-costs/entries?${q.toString()}`
      )
      setEntries(result.data.items)
    } catch (e) {
      console.error('Failed to load entries:', e)
      setEntries([])
      setError((e as ApiError)?.detail || 'Не удалось загрузить записи')
    } finally {
      setEntriesLoading(false)
    }
  }

  useEffect(() => {
    loadEntries()
  }, [projectId, offset, dateFrom, dateTo, filterScope, marketplaceCode, category, nmId, filterInternalSku])

  const loadSummary = async () => {
    if (!summaryDateFrom || !summaryDateTo) {
      setError('Для сводки необходимо указать дату с и дату по')
      return
    }
    try {
      setSummaryLoading(true)
      setError(null)
      const q = new URLSearchParams()
      q.set('date_from', summaryDateFrom)
      q.set('date_to', summaryDateTo)
      q.set('level', summaryLevel)
      if (summaryMarketplaceCode) q.set('marketplace_code', summaryMarketplaceCode)

      const result = await apiGet<AdditionalCostSummaryResponse>(
        `/api/v1/projects/${projectId}/additional-costs/summary?${q.toString()}`
      )
      setSummary(result.data)
    } catch (e) {
      console.error('Failed to load summary:', e)
      setError((e as ApiError)?.detail || 'Не удалось загрузить сводку')
      setSummary(null)
    } finally {
      setSummaryLoading(false)
    }
  }

  const handleAddEntry = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!formPeriodFrom || !formPeriodTo || !formAmount || !formCategory) {
      setError('Обязательны поля: период с, период по, сумма и категория')
      return
    }
    // Validate scope-specific required fields
    if (formScope === 'marketplace' && !formMarketplaceCode) {
      setError('Для маркетплейса необходимо указать код маркетплейса')
      return
    }
    if (formScope === 'product' && !formInternalSku) {
      setError('Для товара необходимо указать артикул (SKU)')
      return
    }
    setError(null)
    setSubmitting(true)
    try {
      const payload: any = {
        scope: formScope,
        period_from: formPeriodFrom,
        period_to: formPeriodTo,
        date_incurred: formDateIncurred || null,
        currency: 'RUB', // Default currency, hidden from UI
        amount: parseFloat(formAmount),
        category: formCategory,
        subcategory: formSubcategory || null,
        vendor: formVendor || null,
        description: formDescription || null,
        source: 'manual',
        external_uid: null,
        payload: {},
      }
      
      // Add scope-specific fields
      if (formScope === 'project') {
        payload.marketplace_code = formMarketplaceCode || null
        payload.internal_sku = null
        payload.nm_id = null
      } else if (formScope === 'marketplace') {
        payload.marketplace_code = formMarketplaceCode || null
        payload.internal_sku = null
        payload.nm_id = null
      } else if (formScope === 'product') {
        payload.marketplace_code = formMarketplaceCode || null
        payload.internal_sku = formInternalSku
        payload.nm_id = formNmId ? parseInt(formNmId) : null
      }
      
      await apiPost(`/api/v1/projects/${projectId}/additional-costs/entries`, payload)
      setToast('Расход добавлен')
      setFormScope('project')
      setFormPeriodFrom('')
      setFormPeriodTo('')
      setFormDateIncurred('')
      setFormAmount('')
      setFormCategory('')
      setFormSubcategory('')
      setFormVendor('')
      setFormDescription('')
      setFormMarketplaceCode('')
      setFormNmId('')
      setFormInternalSku('')
      setTimeout(() => setToast(null), 3000)
      loadEntries()
    } catch (err: unknown) {
      const apiErr = err as ApiError
      setError(apiErr?.detail || 'Не удалось добавить расход')
    } finally {
      setSubmitting(false)
    }
  }

  const handleEdit = (entry: AdditionalCostEntry) => {
    setEditingId(entry.id)
    setEditForm({
      scope: entry.scope,
      period_from: entry.period_from,
      period_to: entry.period_to,
      date_incurred: entry.date_incurred || '',
      amount: typeof entry.amount === 'string' ? parseFloat(entry.amount) : entry.amount,
      category: entry.category,
      subcategory: entry.subcategory || '',
      vendor: entry.vendor || '',
      description: entry.description || '',
      marketplace_code: entry.marketplace_code || '',
      nm_id: entry.nm_id,
      internal_sku: entry.internal_sku || '',
    })
  }

  const handleSaveEdit = async () => {
    if (!editingId) return
    try {
      setError(null)
      const patch: Record<string, any> = {}
      if (editForm.scope) patch.scope = editForm.scope
      if (editForm.period_from) patch.period_from = editForm.period_from
      if (editForm.period_to) patch.period_to = editForm.period_to
      if (editForm.date_incurred !== undefined) patch.date_incurred = editForm.date_incurred || null
      if (editForm.amount !== undefined) patch.amount = editForm.amount
      if (editForm.category) patch.category = editForm.category
      if (editForm.subcategory !== undefined) patch.subcategory = editForm.subcategory || null
      if (editForm.vendor !== undefined) patch.vendor = editForm.vendor || null
      if (editForm.description !== undefined) patch.description = editForm.description || null
      if (editForm.marketplace_code !== undefined) patch.marketplace_code = editForm.marketplace_code || null
      if (editForm.nm_id !== undefined) patch.nm_id = editForm.nm_id
      if (editForm.internal_sku !== undefined) patch.internal_sku = editForm.internal_sku || null

      await apiPut(`/api/v1/additional-costs/entries/${editingId}`, patch)
      setToast('Расход обновлён')
      setEditingId(null)
      setEditForm({})
      setTimeout(() => setToast(null), 3000)
      loadEntries()
    } catch (err: unknown) {
      const apiErr = err as ApiError
      setError(apiErr?.detail || 'Не удалось обновить расход')
    }
  }

  const handleDelete = async (entryId: number) => {
    if (!confirm('Удалить этот расход?')) return
    try {
      await apiDelete(`/api/v1/additional-costs/entries/${entryId}`)
      setToast('Расход удалён')
      setTimeout(() => setToast(null), 3000)
      loadEntries()
    } catch (e) {
      console.error('Delete failed:', e)
      setError((e as ApiError)?.detail || 'Ошибка удаления')
    }
  }

  const handleResetFilters = () => {
    setDateFrom('')
    setDateTo('')
    setFilterScope('')
    setMarketplaceCode('')
    setCategory('')
    setNmId('')
    setFilterInternalSku('')
    setOffset(0)
  }

  const loadProjectMarketplaces = async () => {
    try {
      const result = await apiGet<ProjectMarketplace[]>(`/api/v1/projects/${projectId}/marketplaces`)
      setProjectMarketplaces(result.data.map((pm: any) => ({
        id: pm.id,
        marketplace_code: pm.marketplace_code,
        marketplace_name: pm.marketplace_name || pm.marketplace_code,
      })))
    } catch (e) {
      console.error('Failed to load marketplaces:', e)
    }
  }

  const loadCategories = async () => {
    try {
      const result = await apiGet<AdditionalCostCategoriesResponse>(`/api/v1/projects/${projectId}/additional-costs/categories`)
      setCategories(result.data.categories)
    } catch (e) {
      console.error('Failed to load categories:', e)
    }
  }

  const loadWarehouseDays = async () => {
    if (!warehouseDateFrom || !warehouseDateTo) return
    try {
      setWarehouseDaysLoading(true)
      setError(null)
      const q = new URLSearchParams()
      q.set('date_from', warehouseDateFrom)
      q.set('date_to', warehouseDateTo)
      if (warehouseMarketplaceCode) q.set('marketplace_code', warehouseMarketplaceCode)

      const result = await apiGet<WarehouseLaborDaysListResponse>(
        `/api/v1/projects/${projectId}/warehouse-labor/days?${q.toString()}`
      )
      setWarehouseDays(result.data.items)
    } catch (e) {
      console.error('Failed to load warehouse days:', e)
      setError((e as ApiError)?.detail || 'Не удалось загрузить смены')
      setWarehouseDays([])
    } finally {
      setWarehouseDaysLoading(false)
    }
  }

  useEffect(() => {
    if (warehouseDateFrom && warehouseDateTo) {
      loadWarehouseDays()
    }
  }, [projectId, warehouseDateFrom, warehouseDateTo, warehouseMarketplaceCode])

  const loadWarehouseSummary = async () => {
    if (!warehouseSummaryDateFrom || !warehouseSummaryDateTo) {
      setError('Для сводки необходимо указать дату с и дату по')
      return
    }
    try {
      setWarehouseSummaryLoading(true)
      setError(null)
      const q = new URLSearchParams()
      q.set('date_from', warehouseSummaryDateFrom)
      q.set('date_to', warehouseSummaryDateTo)
      q.set('group_by', warehouseSummaryGroupBy)
      if (warehouseSummaryMarketplaceCode) q.set('marketplace_code', warehouseSummaryMarketplaceCode)

      const result = await apiGet<WarehouseLaborSummaryResponse>(
        `/api/v1/projects/${projectId}/warehouse-labor/summary?${q.toString()}`
      )
      setWarehouseSummary(result.data)
    } catch (e) {
      console.error('Failed to load warehouse summary:', e)
      setError((e as ApiError)?.detail || 'Не удалось загрузить сводку')
      setWarehouseSummary(null)
    } finally {
      setWarehouseSummaryLoading(false)
    }
  }

  const handleWarehouseDayClick = (day: WarehouseLaborDay) => {
    setWarehouseEditingDayId(day.id)
    setWarehouseFormWorkDate(day.work_date)
    setWarehouseFormMarketplaceCode(day.marketplace_code || '')
    setWarehouseFormNotes(day.notes || '')
    setWarehouseFormRates(day.rates.map(r => ({
      rate_name: r.rate_name,
      employees_count: String(r.employees_count),  // Convert to string
      rate_amount: typeof r.rate_amount === 'string' ? r.rate_amount : String(r.rate_amount),  // Convert to string
    })))
  }

  const handleWarehouseCancel = () => {
    setWarehouseEditingDayId(null)
    setWarehouseFormWorkDate('')
    setWarehouseFormMarketplaceCode('')
    setWarehouseFormNotes('')
    setWarehouseFormRates([])
  }

  const handleWarehouseSave = async () => {
    if (!warehouseFormWorkDate) {
      setError('Необходимо указать дату')
      return
    }
    
    // Filter out completely empty rows (no name and no numbers)
    const nonEmptyRates = warehouseFormRates.filter(r => {
      const hasName = r.rate_name && r.rate_name.trim()
      const employeesStr = String(r.employees_count || '').trim()
      const hasEmployees = employeesStr && parseFloat(employeesStr.replace(/\s+/g, '').replace(',', '.')) > 0
      const amountStr = String(r.rate_amount || '').trim()
      const hasAmount = amountStr && parseFloat(amountStr.replace(/\s+/g, '').replace(',', '.')) > 0
      return hasName || hasEmployees || hasAmount
    })
    
    if (nonEmptyRates.length === 0) {
      setError('Необходимо добавить хотя бы одну ставку')
      return
    }
    
    // Normalize and validate each rate
    const validatedRates: Array<{ rate_name: string; employees_count: number; rate_amount: string; _error?: string }> = []
    let hasErrors = false
    
    for (let i = 0; i < nonEmptyRates.length; i++) {
      const rate = nonEmptyRates[i]
      const errors: string[] = []
      
      // Normalize rate_name
      const rateName = rate.rate_name.trim()
      if (!rateName) {
        errors.push('Название ставки не может быть пустым')
      }
      
      // Normalize employees_count
      const employeesStr = String(rate.employees_count).replace(/\s+/g, '').replace(',', '.')
      const employeesCount = parseInt(employeesStr, 10)
      if (isNaN(employeesCount) || employeesCount <= 0) {
        errors.push('Количество сотрудников должно быть больше 0')
      }
      
      // Normalize rate_amount
      const rateAmountStr = String(rate.rate_amount).replace(/\s+/g, '').replace(',', '.')
      const rateAmount = parseFloat(rateAmountStr)
      
      if (isNaN(rateAmount) || rateAmount <= 0) {
        errors.push('Ставка должна быть больше 0')
      }
      
      if (errors.length > 0) {
        hasErrors = true
        // Update error in state
        const newRates = [...warehouseFormRates]
        const originalIndex = warehouseFormRates.findIndex((r, idx) => idx === i || r === rate)
        if (originalIndex >= 0) {
          newRates[originalIndex] = { ...newRates[originalIndex], _error: errors.join('; ') }
          setWarehouseFormRates(newRates)
        }
      } else {
        validatedRates.push({
          rate_name: rateName,
          employees_count: employeesCount,
          rate_amount: rateAmount.toFixed(2),  // Send as string (Decimal-safe)
        })
      }
    }
    
    if (hasErrors) {
      setError('Исправьте ошибки в формах ставок')
      return
    }
    
    setError(null)
    setWarehouseSubmitting(true)
    try {
      const payload: any = {
        work_date: warehouseFormWorkDate,
        marketplace_code: warehouseFormMarketplaceCode || null,
        notes: warehouseFormNotes || null,
        rates: validatedRates,
      }
      
      await apiPost(`/api/v1/projects/${projectId}/warehouse-labor/days`, payload)
      setToast('Смена сохранена')
      setTimeout(() => setToast(null), 3000)
      handleWarehouseCancel()
      loadWarehouseDays()
    } catch (err: unknown) {
      const apiErr = err as ApiError
      setError(apiErr?.detail || 'Не удалось сохранить смену')
    } finally {
      setWarehouseSubmitting(false)
    }
  }

  const handleWarehouseDelete = async (dayId: number) => {
    if (!confirm('Удалить эту смену?')) return
    try {
      await apiDelete(`/api/v1/warehouse-labor/days/${dayId}`)
      setToast('Смена удалена')
      setTimeout(() => setToast(null), 3000)
      loadWarehouseDays()
    } catch (e) {
      console.error('Delete failed:', e)
      setError((e as ApiError)?.detail || 'Ошибка удаления')
    }
  }

  const addWarehouseRate = () => {
    setWarehouseFormRates([...warehouseFormRates, { rate_name: '', employees_count: '1', rate_amount: '0' }])
  }

  const removeWarehouseRate = (index: number) => {
    setWarehouseFormRates(warehouseFormRates.filter((_, i) => i !== index))
  }

  const updateWarehouseRate = (index: number, field: keyof WarehouseLaborRate, value: any) => {
    const newRates = [...warehouseFormRates]
    newRates[index] = { ...newRates[index], [field]: value, _error: undefined }
    setWarehouseFormRates(newRates)
  }

  const calculateWarehouseDayTotal = () => {
    return warehouseFormRates.reduce((sum, r) => {
      const employees = parseFloat(r.employees_count) || 0
      const rate = parseFloat(r.rate_amount) || 0
      return sum + (employees * rate)
    }, 0)
  }

  // Packaging functions
  const loadPackagingSummary = async () => {
    if (!packagingSummaryDateFrom || !packagingSummaryDateTo) {
      setError('Для сводки необходимо указать дату с и дату по')
      return
    }
    try {
      setPackagingSummaryLoading(true)
      setError(null)
      const q = new URLSearchParams()
      q.set('date_from', packagingSummaryDateFrom)
      q.set('date_to', packagingSummaryDateTo)
      q.set('group_by', packagingSummaryGroupBy)
      if (packagingSummaryGroupBy === 'product') {
        // Optional: add internal_sku filter if needed
      }

      const result = await apiGet<PackagingSummaryResponse>(
        `/api/v1/projects/${projectId}/packaging/summary?${q.toString()}`
      )
      setPackagingSummary(result.data)
    } catch (e) {
      console.error('Failed to load packaging summary:', e)
      setError((e as ApiError)?.detail || 'Не удалось загрузить сводку упаковки')
      setPackagingSummary(null)
    } finally {
      setPackagingSummaryLoading(false)
    }
  }

  const loadPackagingTariffs = async () => {
    try {
      setPackagingTariffsLoading(true)
      setError(null)
      const q = new URLSearchParams()
      if (packagingTariffsQuery) q.set('q', packagingTariffsQuery)
      q.set('only_current', String(packagingTariffsOnlyCurrent))
      q.set('limit', '200')
      q.set('offset', '0')

      const result = await apiGet<PackagingTariffsListResponse>(
        `/api/v1/projects/${projectId}/packaging/tariffs?${q.toString()}`
      )
      setPackagingTariffs(result.data.items)
    } catch (e) {
      console.error('Failed to load packaging tariffs:', e)
      setError((e as ApiError)?.detail || 'Не удалось загрузить тарифы упаковки')
      setPackagingTariffs([])
    } finally {
      setPackagingTariffsLoading(false)
    }
  }

  const handlePackagingBulkSubmit = async () => {
    if (!packagingBulkValidFrom) {
      setError('Необходимо указать дату действия')
      return
    }
    if (!packagingBulkCostPerUnit || parseFloat(packagingBulkCostPerUnit) <= 0) {
      setError('Стоимость за единицу должна быть больше 0')
      return
    }
    
    // Parse SKU list
    const skuLines = packagingBulkSkuList.split('\n').map(s => s.trim()).filter(s => s.length > 0)
    if (skuLines.length === 0) {
      setError('Необходимо указать хотя бы один SKU')
      return
    }

    setPackagingBulkSubmitting(true)
    setError(null)
    try {
      const costPerUnit = parseFloat(packagingBulkCostPerUnit.replace(/\s+/g, '').replace(',', '.'))
      if (isNaN(costPerUnit) || costPerUnit <= 0) {
        setError('Стоимость за единицу должна быть положительным числом')
        setPackagingBulkSubmitting(false)
        return
      }

      const result = await apiPost<{created: number, updated: number, skipped: number}>(
        `/api/v1/projects/${projectId}/packaging/tariffs/bulk-upsert`,
        {
          valid_from: packagingBulkValidFrom,
          cost_per_unit: costPerUnit.toFixed(2),
          notes: packagingBulkNotes || null,
          sku_list: skuLines,
        }
      )
      setPackagingBulkResult(result.data)
      setPackagingBulkSkuList('')
      setPackagingBulkCostPerUnit('')
      setPackagingBulkNotes('')
      setTimeout(() => setPackagingBulkResult(null), 5000)
      await loadPackagingTariffs()
    } catch (err: unknown) {
      const apiErr = err as ApiError
      setError(apiErr?.detail || 'Не удалось сохранить тарифы')
    } finally {
      setPackagingBulkSubmitting(false)
    }
  }

  const handlePackagingTariffDelete = async (tariffId: number) => {
    if (!confirm('Удалить этот тариф?')) return
    try {
      await apiDelete(`/api/v1/projects/${projectId}/packaging/tariffs/${tariffId}`)
      setToast('Тариф удален')
      setTimeout(() => setToast(null), 3000)
      await loadPackagingTariffs()
    } catch (e) {
      console.error('Delete failed:', e)
      setError((e as ApiError)?.detail || 'Ошибка удаления')
    }
  }

  const loadPackagingTariffHistory = async (internalSku: string) => {
    try {
      const q = new URLSearchParams()
      q.set('q', internalSku)
      q.set('only_current', 'false')
      q.set('limit', '200')
      q.set('offset', '0')

      const result = await apiGet<PackagingTariffsListResponse>(
        `/api/v1/projects/${projectId}/packaging/tariffs?${q.toString()}`
      )
      return result.data.items.filter(t => t.internal_sku === internalSku)
    } catch (e) {
      console.error('Failed to load tariff history:', e)
      return []
    }
  }

  const handleTabChange = (tab: 'expenses' | 'warehouse' | 'packaging') => {
    const params = new URLSearchParams(searchParams.toString())
    params.set('tab', tab)
    const newUrl = `${window.location.pathname}?${params.toString()}`
    router.push(newUrl)
  }

  return (
    <div className={[s.root, 'container'].join(' ')}>
      <h1>Управление расходами</h1>
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

      {/* Summary Section - объединенная сводка */}
      <div className="card" style={{ marginTop: 24 }}>
        <h2>Сводка расходов</h2>
        <div className={s.gridSummary}>
          <Field label="Дата с">
            <InputDate value={summaryDateFrom} onChange={(e) => setSummaryDateFrom(e.target.value)} />
          </Field>
          <Field label="Дата по">
            <InputDate value={summaryDateTo} onChange={(e) => setSummaryDateTo(e.target.value)} />
          </Field>
          <Field label="Группировка">
            <SelectBase value={summaryLevel} onChange={(e) => setSummaryLevel(e.target.value as typeof summaryLevel)}>
              <option value="project">Проект</option>
              <option value="marketplace">Маркетплейс</option>
              <option value="product">Товар</option>
            </SelectBase>
          </Field>
          {summaryLevel === 'product' && (
            <Field label="Маркетплейс">
              <SelectBase value={summaryMarketplaceCode} onChange={(e) => setSummaryMarketplaceCode(e.target.value)}>
                <option value="">Все</option>
                <option value="">Общий</option>
                {projectMarketplaces.map((pm) => (
                  <option key={pm.id} value={pm.marketplace_code}>
                    {pm.marketplace_name}
                  </option>
                ))}
              </SelectBase>
            </Field>
          )}
          <div className={s.gridSummaryButton}>
            <ButtonBase onClick={loadSummary} disabled={summaryLoading}>
              {summaryLoading ? 'Загрузка…' : 'Показать сводку'}
            </ButtonBase>
          </div>
        </div>
        <p style={{ fontSize: '0.9rem', color: '#666', marginTop: 8 }}>
          Распределение: по дням
        </p>
            {summary && (
          <div style={{ marginTop: 12 }}>
            <p style={{ marginBottom: 12 }}>
              <strong>
                Итого: {typeof summary.total_amount === 'number' 
                  ? summary.total_amount.toFixed(2) 
                  : typeof summary.total_amount === 'string' 
                    ? parseFloat(summary.total_amount).toFixed(2) 
                    : '0.00'}
              </strong>
            </p>
            {summary.breakdown.length > 0 ? (
              <table style={{ marginTop: 12 }}>
                <thead>
                  <tr>
                    {summaryLevel === 'project' && (
                      <>
                        <th>Категория</th>
                        <th>Подкатегория</th>
                      </>
                    )}
                    {summaryLevel === 'marketplace' && (
                      <>
                        <th>Маркетплейс</th>
                        <th>Категория</th>
                        <th>Подкатегория</th>
                      </>
                    )}
                    {summaryLevel === 'product' && (
                      <>
                        <th>Артикул (SKU)</th>
                        <th>Категория</th>
                        <th>Подкатегория</th>
                        <th>nm_id</th>
                      </>
                    )}
                    <th>Сумма</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.breakdown.map((item, idx) => (
                    <tr key={idx}>
                      {summaryLevel === 'project' && (
                        <>
                          <td>{item.category}</td>
                          <td>{item.subcategory || '—'}</td>
                        </>
                      )}
                      {summaryLevel === 'marketplace' && (
                        <>
                          <td>{item.marketplace_code || '—'}</td>
                          <td>{item.category}</td>
                          <td>{item.subcategory || '—'}</td>
                        </>
                      )}
                      {summaryLevel === 'product' && (
                        <>
                          <td>{item.internal_sku || '—'}</td>
                          <td>{item.category}</td>
                          <td>{item.subcategory || '—'}</td>
                          <td>{item.nm_id || '—'}</td>
                        </>
                      )}
                      <td>
                        {typeof item.prorated_amount === 'number' 
                          ? item.prorated_amount.toFixed(2) 
                          : typeof item.prorated_amount === 'string' 
                            ? parseFloat(item.prorated_amount).toFixed(2) 
                            : '0.00'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p style={{ color: '#666' }}>Нет данных</p>
            )}
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className={s.gridTabs}>
        <button
          type="button"
          onClick={() => handleTabChange('expenses')}
          className={[s.tab, activeTab === 'expenses' && s.tabActive].filter(Boolean).join(' ')}
        >
          Расходы
        </button>
        <button
          type="button"
          onClick={() => handleTabChange('warehouse')}
          className={[s.tab, activeTab === 'warehouse' && s.tabActive].filter(Boolean).join(' ')}
        >
          Склад
        </button>
        <button
          type="button"
          onClick={() => handleTabChange('packaging')}
          className={[s.tab, activeTab === 'packaging' && s.tabActive].filter(Boolean).join(' ')}
        >
          Упаковка
        </button>
      </div>

      {/* Tab: Expenses */}
      {activeTab === 'expenses' && (
        <>
          {/* Add Entry Form */}
          <div className="card" style={{ marginTop: 16 }}>
            <h2>Добавить расход</h2>
        <form onSubmit={handleAddEntry}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, minmax(120px, 1fr))', gap: 12, marginBottom: 12 }}>
            <Field label="Куда относится">
              <SelectBase
                value={formScope}
                onChange={(e) => {
                  const newScope = e.target.value as typeof formScope
                  setFormScope(newScope)
                  // Clear scope-specific fields when scope changes
                  if (newScope === 'project') {
                    setFormMarketplaceCode('')
                    setFormInternalSku('')
                    setFormNmId('')
                  } else if (newScope === 'marketplace') {
                    setFormInternalSku('')
                    setFormNmId('')
                  } else if (newScope === 'product') {
                    // Keep marketplace_code and nm_id, but clear if needed
                  }
                }}
              >
                <option value="project">Проект</option>
                <option value="marketplace">Маркетплейс</option>
                <option value="product">Товар</option>
              </SelectBase>
            </Field>
            <Field label="Период с">
              <InputDate value={formPeriodFrom} onChange={(e) => setFormPeriodFrom(e.target.value)} required />
            </Field>
            <Field label="Период по">
              <InputDate value={formPeriodTo} onChange={(e) => setFormPeriodTo(e.target.value)} required />
            </Field>
            <Field label="Дата расхода">
              <InputDate value={formDateIncurred} onChange={(e) => setFormDateIncurred(e.target.value)} />
            </Field>
          </div>
          <div className={s.gridFormRow1}>
            <Field label="Сумма">
              <InputBase
                type="number"
                step="0.01"
                value={formAmount}
                onChange={(e) => setFormAmount(e.target.value)}
                required
              />
            </Field>
            <Field label="Категория">
              <SelectBase value={formCategory} onChange={(e) => { setFormCategory(e.target.value); setFormSubcategory('') }} required>
                <option value="">Выберите категорию</option>
                {categories.map((cat) => (
                  <option key={cat.name} value={cat.name}>
                    {cat.name}
                  </option>
                ))}
              </SelectBase>
            </Field>
            <Field label="Подкатегория">
              {formCategory && categories.find(c => c.name === formCategory) ? (
                <SelectBase value={formSubcategory} onChange={(e) => setFormSubcategory(e.target.value)}>
                  <option value="">Выберите подкатегорию</option>
                  {categories.find(c => c.name === formCategory)?.subcategories.map((sub) => (
                    <option key={sub} value={sub}>
                      {sub}
                    </option>
                  ))}
                </SelectBase>
              ) : (
                <InputBase type="text" value={formSubcategory} onChange={(e) => setFormSubcategory(e.target.value)} placeholder="Введите подкатегорию" />
              )}
            </Field>
            <Field label="Поставщик">
              <InputBase type="text" value={formVendor} onChange={(e) => setFormVendor(e.target.value)} />
            </Field>
            <Field label="Комментарий" className={s.gridFormDescription}>
              <InputBase type="text" value={formDescription} onChange={(e) => setFormDescription(e.target.value)} />
            </Field>
          </div>
          <div className={s.gridFormRow3}>
            {formScope === 'project' && (
              <Field label="Маркетплейс">
                <SelectBase value={formMarketplaceCode} onChange={(e) => setFormMarketplaceCode(e.target.value)}>
                  <option value="">Общий</option>
                  {projectMarketplaces.map((pm) => (
                    <option key={pm.id} value={pm.marketplace_code}>
                      {pm.marketplace_name}
                    </option>
                  ))}
                </SelectBase>
              </Field>
            )}
            {formScope === 'marketplace' && (
              <Field label="Маркетплейс">
                <SelectBase value={formMarketplaceCode} onChange={(e) => setFormMarketplaceCode(e.target.value)} required>
                  <option value="">Выберите маркетплейс</option>
                  {projectMarketplaces.map((pm) => (
                    <option key={pm.id} value={pm.marketplace_code}>
                      {pm.marketplace_name}
                    </option>
                  ))}
                </SelectBase>
              </Field>
            )}
            {formScope === 'product' && (
              <>
                <Field label="Артикул (SKU)">
                  <InputBase type="text" value={formInternalSku} onChange={(e) => setFormInternalSku(e.target.value)} required />
                </Field>
                <Field label="nm_id">
                  <InputBase type="number" value={formNmId} onChange={(e) => setFormNmId(e.target.value)} />
                </Field>
                <Field label="Маркетплейс">
                  <SelectBase value={formMarketplaceCode} onChange={(e) => setFormMarketplaceCode(e.target.value)}>
                    <option value="">Выберите маркетплейс</option>
                    {projectMarketplaces.map((pm) => (
                      <option key={pm.id} value={pm.marketplace_code}>
                        {pm.marketplace_name}
                      </option>
                    ))}
                  </SelectBase>
                </Field>
              </>
            )}
            <div className={s.gridFormButton}>
              <ButtonBase type="submit" disabled={submitting}>
                {submitting ? 'Добавление…' : 'Добавить'}
              </ButtonBase>
            </div>
          </div>
        </form>
          </div>

          {/* Entries List with compact filters */}
          <div className="card" style={{ marginTop: 16 }}>
            <h2>Расходы</h2>
            {/* Compact filters row */}
            <div className={s.gridFiltersCompact}>
              <Field label="Дата с">
                <InputDate value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
              </Field>
              <Field label="Дата по">
                <InputDate value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
              </Field>
              <Field label="Куда относится">
                <SelectBase value={filterScope} onChange={(e) => setFilterScope(e.target.value)}>
                  <option value="">Все</option>
                  <option value="project">Проект</option>
                  <option value="marketplace">Маркетплейс</option>
                  <option value="product">Товар</option>
                </SelectBase>
              </Field>
              <Field label="Маркетплейс">
                <SelectBase value={marketplaceCode} onChange={(e) => setMarketplaceCode(e.target.value)}>
                  <option value="">Все</option>
                  <option value="">Общий</option>
                  {projectMarketplaces.map((pm) => (
                    <option key={pm.id} value={pm.marketplace_code}>
                      {pm.marketplace_name}
                    </option>
                  ))}
                </SelectBase>
              </Field>
              <Field label="Категория">
                <InputBase type="text" value={category} onChange={(e) => setCategory(e.target.value)} />
              </Field>
              <Field label="nm_id">
                <InputBase type="number" value={nmId} onChange={(e) => setNmId(e.target.value)} />
              </Field>
              <Field label="Артикул (SKU)">
                <InputBase type="text" value={filterInternalSku} onChange={(e) => setFilterInternalSku(e.target.value)} />
              </Field>
              <div className={s.gridFiltersCompactButtons}>
                <ButtonBase onClick={() => setOffset(0)}>Применить</ButtonBase>
                <ButtonBase variant="secondary" onClick={handleResetFilters}>
                  Сбросить
                </ButtonBase>
              </div>
            </div>
        {entriesLoading ? (
          <p>Загрузка…</p>
        ) : (
          <>
            {entries.length === 0 ? (
              <div className={s.emptyState}>
                <div className={s.emptyStateTitle}>Расходов пока нет</div>
                <div className={s.emptyStateText}>
                  Добавьте первую запись через форму выше или настройте фильтры.
                </div>
              </div>
            ) : (
              <>
                <div style={{ overflowX: 'auto' }}>
                  <table>
                    <thead>
                      <tr>
                        <th>Куда относится</th>
                        <th>Период</th>
                        <th>Дата расхода</th>
                        <th>Сумма</th>
                        <th>Категория / Подкатегория</th>
                        <th>Маркетплейс</th>
                        <th>Товар</th>
                        <th>Поставщик</th>
                        <th>Комментарий</th>
                        <th>Действия</th>
                      </tr>
                    </thead>
                    <tbody>
                      {entries.map((entry) =>
                        editingId === entry.id ? (
                          <tr key={entry.id}>
                            <td colSpan={10}>
                              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, padding: 8, alignItems: 'flex-end' }}>
                                <Field label="Куда относится">
                                  <SelectBase
                                    value={editForm.scope || entry.scope}
                                    onChange={(e) => setEditForm({ ...editForm, scope: e.target.value as typeof entry.scope })}
                                  >
                                    <option value="project">Проект</option>
                                    <option value="marketplace">Маркетплейс</option>
                                    <option value="product">Товар</option>
                                  </SelectBase>
                                </Field>
                                <Field label="Период с">
                                  <InputDate
                                    value={editForm.period_from || ''}
                                    onChange={(e) => setEditForm({ ...editForm, period_from: e.target.value })}
                                  />
                                </Field>
                                <Field label="Период по">
                                  <InputDate
                                    value={editForm.period_to || ''}
                                    onChange={(e) => setEditForm({ ...editForm, period_to: e.target.value })}
                                  />
                                </Field>
                                <Field label="Сумма">
                                  <InputBase
                                    type="number"
                                    step="0.01"
                                    value={String(editForm.amount || '')}
                                    onChange={(e) => setEditForm({ ...editForm, amount: parseFloat(e.target.value) })}
                                  />
                                </Field>
                                <Field label="Категория">
                                  <InputBase
                                    value={editForm.category || ''}
                                    onChange={(e) => setEditForm({ ...editForm, category: e.target.value })}
                                  />
                                </Field>
                                {(editForm.scope || entry.scope) === 'marketplace' && (
                                  <Field label="Маркетплейс">
                                    <InputBase
                                      type="text"
                                      value={editForm.marketplace_code || ''}
                                      onChange={(e) => setEditForm({ ...editForm, marketplace_code: e.target.value })}
                                    />
                                  </Field>
                                )}
                                {(editForm.scope || entry.scope) === 'product' && (
                                  <>
                                    <Field label="Артикул (SKU)">
                                      <InputBase
                                        type="text"
                                        value={editForm.internal_sku || ''}
                                        onChange={(e) => setEditForm({ ...editForm, internal_sku: e.target.value })}
                                      />
                                    </Field>
                                    <Field label="nm_id">
                                      <InputBase
                                        type="number"
                                        value={String(editForm.nm_id || '')}
                                        onChange={(e) => setEditForm({ ...editForm, nm_id: e.target.value ? parseInt(e.target.value) : null })}
                                      />
                                    </Field>
                                  </>
                                )}
                                <ButtonBase onClick={handleSaveEdit}>Сохранить</ButtonBase>
                                <ButtonBase variant="secondary" onClick={() => setEditingId(null)}>
                                  Отмена
                                </ButtonBase>
                              </div>
                            </td>
                          </tr>
                        ) : (
                          <tr key={entry.id}>
                            <td>
                              {entry.scope === 'project' ? 'Проект' : entry.scope === 'marketplace' ? 'Маркетплейс' : 'Товар'}
                            </td>
                            <td>
                              {entry.period_from} — {entry.period_to}
                            </td>
                            <td>{entry.date_incurred || '—'}</td>
                            <td>
                              {typeof entry.amount === 'number' 
                                ? entry.amount.toFixed(2) 
                                : typeof entry.amount === 'string' 
                                  ? parseFloat(entry.amount).toFixed(2) 
                                  : '—'}
                            </td>
                            <td>
                              {entry.category}
                              {entry.subcategory && ` / ${entry.subcategory}`}
                            </td>
                            <td>{entry.marketplace_code || '—'}</td>
                            <td>
                              {entry.internal_sku || '—'}
                              {entry.internal_sku && entry.nm_id && ` (nm_id: ${entry.nm_id})`}
                              {!entry.internal_sku && entry.nm_id && `nm_id: ${entry.nm_id}`}
                            </td>
                            <td>{entry.vendor || '—'}</td>
                            <td>{entry.description || '—'}</td>
                            <td className={s.tableActionsCell}>
                              <ButtonBase
                                variant="secondary"
                                className={s.tableActionBtn}
                                onClick={() => handleEdit(entry)}
                              >
                                Изменить
                              </ButtonBase>
                              <ButtonBase
                                variant="secondary"
                                className={s.tableActionBtn}
                                onClick={() => handleDelete(entry.id)}
                              >
                                Удалить
                              </ButtonBase>
                            </td>
                          </tr>
                        )
                      )}
                    </tbody>
                  </table>
                </div>
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
                    Страница {Math.floor(offset / limit) + 1}
                  </span>
                  <button
                    type="button"
                    className={s.paginationBtn}
                    onClick={() => setOffset(offset + limit)}
                    disabled={entries.length < limit}
                  >
                    Вперёд
                  </button>
                </div>
              </>
            )}
          </>
        )}
          </div>
        </>
      )}

      {/* Tab: Warehouse */}
      {activeTab === 'warehouse' && (
        <>
          {/* Warehouse Form */}
          <div className="card" style={{ marginTop: 16 }}>
            <h2>{warehouseEditingDayId ? 'Редактировать смену' : 'Добавить смену'}</h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(150px, 1fr))', gap: 12, marginBottom: 12 }}>
            <Field label="Дата">
              <InputDate
                value={warehouseFormWorkDate}
                onChange={(e) => setWarehouseFormWorkDate(e.target.value)}
                required
                disabled={!!warehouseEditingDayId}
              />
            </Field>
            <Field label="Маркетплейс">
              <SelectBase
                value={warehouseFormMarketplaceCode}
                onChange={(e) => setWarehouseFormMarketplaceCode(e.target.value)}
                disabled={!!warehouseEditingDayId}
              >
                <option value="">Общий</option>
                {projectMarketplaces.map((pm) => (
                  <option key={pm.id} value={pm.marketplace_code}>
                    {pm.marketplace_name}
                  </option>
                ))}
              </SelectBase>
            </Field>
            <Field label="Примечания">
              <InputBase
                type="text"
                value={warehouseFormNotes}
                onChange={(e) => setWarehouseFormNotes(e.target.value)}
              />
            </Field>
          </div>
          <div style={{ marginBottom: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <strong>Ставки</strong>
              <ButtonBase onClick={addWarehouseRate} variant="secondary">
                + Добавить строку
              </ButtonBase>
            </div>
            {warehouseFormRates.length > 0 ? (
              <table style={{ width: '100%' }}>
                <thead>
                  <tr>
                    <th>Название ставки</th>
                    <th>Кол-во сотрудников</th>
                    <th>Ставка (руб)</th>
                    <th>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {warehouseFormRates.map((rate, idx) => (
                    <tr key={idx}>
                      <td>
                        <InputBase
                          type="text"
                          value={rate.rate_name}
                          onChange={(e) => updateWarehouseRate(idx, 'rate_name', e.target.value)}
                          required
                        />
                        {rate._error && rate._error.includes('Название') && (
                          <div style={{ fontSize: '12px', color: '#dc3545', marginTop: '4px' }}>
                            {rate._error}
                          </div>
                        )}
                      </td>
                      <td>
                        <InputBase
                          type="text"
                          value={rate.employees_count}
                          onChange={(e) => updateWarehouseRate(idx, 'employees_count', e.target.value)}
                          required
                        />
                        {rate._error && rate._error.includes('сотрудников') && (
                          <div style={{ fontSize: '12px', color: '#dc3545', marginTop: '4px' }}>
                            {rate._error}
                          </div>
                        )}
                      </td>
                      <td>
                        <InputBase
                          type="text"
                          value={rate.rate_amount}
                          onChange={(e) => updateWarehouseRate(idx, 'rate_amount', e.target.value)}
                          required
                        />
                        {rate._error && rate._error.includes('Ставка') && (
                          <div style={{ fontSize: '12px', color: '#dc3545', marginTop: '4px' }}>
                            {rate._error}
                          </div>
                        )}
                      </td>
                      <td>
                        <ButtonBase onClick={() => removeWarehouseRate(idx)} variant="secondary">
                          Удалить
                        </ButtonBase>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p style={{ color: '#666' }}>Добавьте хотя бы одну ставку</p>
            )}
            {warehouseFormRates.length > 0 && (
              <p style={{ marginTop: 8, fontWeight: 'bold' }}>
                Сумма смены: {calculateWarehouseDayTotal().toFixed(2)} руб.
              </p>
            )}
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <ButtonBase onClick={handleWarehouseSave} disabled={warehouseSubmitting}>
              {warehouseSubmitting ? 'Сохранение…' : warehouseEditingDayId ? 'Сохранить изменения' : 'Сохранить смену'}
            </ButtonBase>
            {warehouseEditingDayId && (
              <>
                <ButtonBase onClick={handleWarehouseCancel} variant="secondary">
                  Отмена
                </ButtonBase>
                <ButtonBase
                  onClick={() => handleWarehouseDelete(warehouseEditingDayId)}
                  variant="secondary"
                >
                  Удалить смену
                </ButtonBase>
              </>
            )}
          </div>
          </div>

          {/* Warehouse Days List with compact filters */}
          <div className="card" style={{ marginTop: 16 }}>
            <h2>Смены</h2>
            {/* Compact filters row */}
            <div className={s.gridFiltersCompact}>
              <Field label="Дата с">
                <InputDate value={warehouseDateFrom} onChange={(e) => setWarehouseDateFrom(e.target.value)} />
              </Field>
              <Field label="Дата по">
                <InputDate value={warehouseDateTo} onChange={(e) => setWarehouseDateTo(e.target.value)} />
              </Field>
              <Field label="Маркетплейс">
                <SelectBase value={warehouseMarketplaceCode} onChange={(e) => setWarehouseMarketplaceCode(e.target.value)}>
                  <option value="">Все</option>
                  <option value="">Общий</option>
                  {projectMarketplaces.map((pm) => (
                    <option key={pm.id} value={pm.marketplace_code}>
                      {pm.marketplace_name}
                    </option>
                  ))}
                </SelectBase>
              </Field>
            </div>
          {warehouseDaysLoading ? (
            <p>Загрузка…</p>
          ) : (
            <>
              {warehouseDays.length === 0 ? (
                <div className={s.emptyState}>
                  <div className={s.emptyStateTitle}>Смен пока нет</div>
                  <div className={s.emptyStateText}>
                    Добавьте первую смену через форму выше или настройте фильтры.
                  </div>
                </div>
              ) : (
                <div style={{ overflowX: 'auto' }}>
                  <table>
                    <thead>
                      <tr>
                        <th>Дата</th>
                        <th>Маркетплейс</th>
                        <th>Ставок</th>
                        <th>Сотрудников</th>
                        <th>Сумма</th>
                        <th>Примечания</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {warehouseDays.map((day) => (
                        <tr
                          key={day.id}
                          onClick={() => handleWarehouseDayClick(day)}
                          style={{ cursor: 'pointer' }}
                        >
                          <td>{day.work_date}</td>
                          <td>{day.marketplace_code || 'Общий'}</td>
                          <td>{day.rates.length}</td>
                          <td>{day.rates.reduce((sum, r) => sum + r.employees_count, 0)}</td>
                          <td>{parseFloat(day.total_amount).toFixed(2)}</td>
                          <td>{day.notes || '—'}</td>
                          <td onClick={(e) => e.stopPropagation()}>
                            <ButtonBase
                              onClick={() => handleWarehouseDelete(day.id)}
                              variant="secondary"
                            >
                              Удалить
                            </ButtonBase>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
          </div>
        </>
      )}

      {activeTab === 'packaging' && (
        <>
          {/* Packaging Summary Card */}
          <div className="card" style={{ marginTop: 16 }}>
            <h2>Упаковка за период</h2>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(150px, 1fr))', gap: 12, marginBottom: 12 }}>
              <Field label="Дата с">
                <InputDate value={packagingSummaryDateFrom} onChange={(e) => setPackagingSummaryDateFrom(e.target.value)} />
              </Field>
              <Field label="Дата по">
                <InputDate value={packagingSummaryDateTo} onChange={(e) => setPackagingSummaryDateTo(e.target.value)} />
              </Field>
              <Field label="Группировка">
                <SelectBase value={packagingSummaryGroupBy} onChange={(e) => setPackagingSummaryGroupBy(e.target.value as 'project' | 'product')}>
                  <option value="project">По проекту</option>
                  <option value="product">По товарам</option>
                </SelectBase>
              </Field>
              <Field label="">
                <ButtonBase onClick={loadPackagingSummary} disabled={packagingSummaryLoading}>
                  {packagingSummaryLoading ? 'Загрузка...' : 'Показать'}
                </ButtonBase>
              </Field>
            </div>
            {packagingSummary && (
              <>
                <p>
                  <strong>
                    Итого: {typeof packagingSummary.total_amount === 'number' 
                      ? packagingSummary.total_amount.toFixed(2) 
                      : typeof packagingSummary.total_amount === 'string' 
                        ? parseFloat(packagingSummary.total_amount).toFixed(2) 
                        : '0.00'} ₽
                  </strong>
                </p>
                {packagingSummaryGroupBy === 'product' && packagingSummary.breakdown.length > 0 && (
                  <table style={{ marginTop: 12 }}>
                    <thead>
                      <tr>
                        <th>SKU</th>
                        <th>Продано шт</th>
                        <th>Упаковка ₽</th>
                      </tr>
                    </thead>
                    <tbody>
                      {packagingSummary.breakdown.map((item, idx) => (
                        <tr key={idx}>
                          <td>{item.internal_sku}</td>
                          <td>{item.units_sold}</td>
                          <td>{typeof item.amount === 'number' ? item.amount.toFixed(2) : typeof item.amount === 'string' ? parseFloat(item.amount).toFixed(2) : '0.00'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                {packagingSummary.breakdown.length === 0 && packagingSummaryGroupBy === 'product' && (
                  <p style={{ marginTop: 12, color: '#666' }}>Нет продаж в периоде</p>
                )}
                {packagingSummary.missing_tariff.count > 0 && (
                  <div style={{ marginTop: 12, padding: 12, backgroundColor: '#fff3cd', borderRadius: 4 }}>
                    <p style={{ margin: 0, fontWeight: 'bold' }}>
                      SKU без тарифа: {packagingSummary.missing_tariff.count}
                    </p>
                    {packagingSummary.missing_tariff.skus.length > 0 && (
                      <details style={{ marginTop: 8 }}>
                        <summary style={{ cursor: 'pointer', fontWeight: 'bold' }}>Показать список</summary>
                        <ul style={{ marginTop: 8, marginLeft: 20 }}>
                          {packagingSummary.missing_tariff.skus.map((sku, idx) => (
                            <li key={idx}>{sku}</li>
                          ))}
                        </ul>
                      </details>
                    )}
                  </div>
                )}
                <p style={{ marginTop: 12, fontSize: '12px', color: '#666' }}>
                  Основание: проданные штуки. Тариф берётся по последней дате valid_from ≤ дата продажи. До первого valid_from стоимость = 0.
                </p>
              </>
            )}
          </div>

          {/* Packaging Bulk Upsert Card */}
          <div className="card" style={{ marginTop: 16 }}>
            <h2>Назначить тарифы</h2>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(150px, 1fr))', gap: 12, marginBottom: 12 }}>
              <Field label="Действует с">
                <InputDate value={packagingBulkValidFrom} onChange={(e) => setPackagingBulkValidFrom(e.target.value)} required />
              </Field>
              <Field label="Стоимость за единицу (₽)">
                <InputBase
                  type="text"
                  value={packagingBulkCostPerUnit}
                  onChange={(e) => setPackagingBulkCostPerUnit(e.target.value)}
                  placeholder="0.00"
                  required
                />
              </Field>
              <Field label="Примечания">
                <InputBase
                  type="text"
                  value={packagingBulkNotes}
                  onChange={(e) => setPackagingBulkNotes(e.target.value)}
                />
              </Field>
            </div>
            <Field label="Список SKU (один на строку)">
              <textarea
                value={packagingBulkSkuList}
                onChange={(e) => setPackagingBulkSkuList(e.target.value)}
                placeholder="SKU1&#10;SKU2&#10;SKU3"
                rows={6}
                style={{ width: '100%', padding: 8, fontFamily: 'monospace' }}
                required
              />
            </Field>
            <div style={{ marginTop: 12 }}>
              <ButtonBase onClick={handlePackagingBulkSubmit} disabled={packagingBulkSubmitting}>
                {packagingBulkSubmitting ? 'Сохранение...' : 'Применить к SKU'}
              </ButtonBase>
            </div>
            {packagingBulkResult && (
              <div style={{ marginTop: 12, padding: 12, backgroundColor: '#d4edda', borderRadius: 4 }}>
                <p style={{ margin: 0 }}>
                  Создано: {packagingBulkResult.created}, Обновлено: {packagingBulkResult.updated}, Пропущено: {packagingBulkResult.skipped}
                </p>
              </div>
            )}
          </div>

          {/* Packaging Tariffs List Card */}
          <div className="card" style={{ marginTop: 16 }}>
            <h2>Тарифы упаковки</h2>
            <div className={s.gridFiltersCompact} style={{ marginBottom: 12 }}>
              <Field label="Поиск по SKU">
                <InputBase
                  type="text"
                  value={packagingTariffsQuery}
                  onChange={(e) => setPackagingTariffsQuery(e.target.value)}
                  placeholder="SKU..."
                />
              </Field>
              <Field label="">
                <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input
                    type="checkbox"
                    checked={packagingTariffsOnlyCurrent}
                    onChange={(e) => setPackagingTariffsOnlyCurrent(e.target.checked)}
                  />
                  Только актуальные
                </label>
              </Field>
              <Field label="">
                <ButtonBase onClick={loadPackagingTariffs} disabled={packagingTariffsLoading}>
                  {packagingTariffsLoading ? 'Загрузка...' : 'Обновить'}
                </ButtonBase>
              </Field>
            </div>
            {packagingTariffsLoading ? (
              <p>Загрузка…</p>
            ) : (
              <>
                {packagingTariffs.length === 0 ? (
                  <div className={s.emptyState}>
                    <div className={s.emptyStateTitle}>Тарифов пока нет</div>
                    <div className={s.emptyStateText}>
                      Используйте форму выше для массовой установки тарифов
                    </div>
                  </div>
                ) : (
                  <table>
                    <thead>
                      <tr>
                        <th>SKU</th>
                        <th>Тариф (₽/шт)</th>
                        <th>Действует с</th>
                        <th>Действия</th>
                      </tr>
                    </thead>
                    <tbody>
                      {packagingTariffs.map((tariff) => (
                        <tr key={tariff.id}>
                          <td>{tariff.internal_sku}</td>
                          <td>{typeof tariff.cost_per_unit === 'number' ? tariff.cost_per_unit.toFixed(2) : typeof tariff.cost_per_unit === 'string' ? parseFloat(tariff.cost_per_unit).toFixed(2) : '0.00'}</td>
                          <td>{tariff.valid_from}</td>
                          <td>
                            {!packagingTariffsOnlyCurrent && (
                              <button
                                type="button"
                                onClick={async () => {
                                  const history = await loadPackagingTariffHistory(tariff.internal_sku)
                                  if (history.length > 0) {
                                    const historyText = history.map(h => `${h.valid_from}: ${typeof h.cost_per_unit === 'number' ? h.cost_per_unit.toFixed(2) : parseFloat(String(h.cost_per_unit)).toFixed(2)} ₽`).join('\n')
                                    alert(`История тарифов для ${tariff.internal_sku}:\n${historyText}`)
                                  } else {
                                    alert('История не найдена')
                                  }
                                }}
                                style={{ marginRight: 8, padding: '4px 8px', fontSize: '12px' }}
                              >
                                История
                              </button>
                            )}
                            {membership?.role === 'admin' || membership?.role === 'owner' ? (
                              <button
                                type="button"
                                onClick={() => handlePackagingTariffDelete(tariff.id)}
                                style={{ padding: '4px 8px', fontSize: '12px', color: '#dc3545' }}
                              >
                                Удалить
                              </button>
                            ) : null}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </>
            )}
          </div>
        </>
      )}
    </div>
  )
}
