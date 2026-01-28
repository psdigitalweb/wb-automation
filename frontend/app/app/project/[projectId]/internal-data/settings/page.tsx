'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { apiGet, apiPost, apiPut } from '../../../../../../lib/apiClient'
import { getAccessToken } from '../../../../../../lib/auth'
import { getApiBase } from '../../../../../../lib/api'
import { usePageTitle } from '../../../../../../hooks/usePageTitle'

interface InternalDataSourceField {
  key: string
  label: string
  kind: 'column' | 'attribute'
}

interface InternalDataSettings {
  project_id: number
  is_enabled: boolean
  source_mode: 'url' | 'upload' | null
  source_url: string | null
  file_storage_key: string | null
  file_original_name: string | null
  file_format: string | null
  last_sync_at: string | null
  last_sync_status: string | null
  last_sync_error: string | null
  last_test_at: string | null
  last_test_status: string | null
  mapping_json: any // always an object from API
}

export default function InternalDataSettingsPage({ params }: { params: { projectId: string } }) {
  const projectId = params.projectId
  usePageTitle('Загрузка каталога', projectId)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [internalData, setInternalData] = useState<InternalDataSettings | null>(null)
  const [internalLoading, setInternalLoading] = useState(false)
  const [internalError, setInternalError] = useState<string | null>(null)
  const [internalModeDraft, setInternalModeDraft] = useState<'url' | 'upload' | ''>('')
  const [internalUrlDraft, setInternalUrlDraft] = useState('')
  const [internalEnabledDraft, setInternalEnabledDraft] = useState(false)
  const [internalTesting, setInternalTesting] = useState(false)
  const [internalTestResult, setInternalTestResult] = useState<string | null>(null)
  const [internalSyncing, setInternalSyncing] = useState(false)
  const [internalUploading, setInternalUploading] = useState(false)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [showMappingWizard, setShowMappingWizard] = useState(false)
  const [mappingDraft, setMappingDraft] = useState<any>({})
  const [mappingPreview, setMappingPreview] = useState<{ rows: any[]; errors: { row_index: number; message: string }[] } | null>(null)
  const [mappingLoading, setMappingLoading] = useState(false)
  const [sourceFields, setSourceFields] = useState<InternalDataSourceField[]>([])
  const [sourceFieldsLoading, setSourceFieldsLoading] = useState(false)
  const [sourceFieldsError, setSourceFieldsError] = useState<string | null>(null)
  const [sourceFieldsErrorType, setSourceFieldsErrorType] = useState<SourceFieldsErrorType | null>(null)
  const [sourceFieldsSampleRows, setSourceFieldsSampleRows] = useState<any[]>([])
  const [showSampleRows, setShowSampleRows] = useState(false)
  const [skuKey, setSkuKey] = useState('')
  const [rrpKey, setRrpKey] = useState('')
  const [stockKey, setStockKey] = useState('')
  const [barcodeKey, setBarcodeKey] = useState('')
  const [skuStrip, setSkuStrip] = useState(true)
  const [skuLastSegment, setSkuLastSegment] = useState(false)
  const [rrpStrip, setRrpStrip] = useState(true)
  const [rrpToDecimal, setRrpToDecimal] = useState(true)
  const [stockStrip, setStockStrip] = useState(true)
  const [stockToInt, setStockToInt] = useState(true)
  const [barcodeStrip, setBarcodeStrip] = useState(true)
  const [showAdvancedMapping, setShowAdvancedMapping] = useState(false)
  const [syncResult, setSyncResult] = useState<{
    snapshot_id: number | null
    rows_total: number | null
    rows_imported: number | null
    rows_failed: number | null
    errors_preview: Array<{ row_index: number; message: string; source_key?: string }> | null
  } | null>(null)
  const [showSyncErrors, setShowSyncErrors] = useState(false)
  const [syncErrorsData, setSyncErrorsData] = useState<{
    total: number
    items: Array<{
      id: number
      row_index: number
      source_key: string | null
      raw_row: any
      error_code: string | null
      message: string
      transforms: string[] | null
      trace: any
      created_at: string
    }>
  } | null>(null)
  const [syncErrorsLoading, setSyncErrorsLoading] = useState(false)
  const [syncErrorsOffset, setSyncErrorsOffset] = useState(0)

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true)
        setError(null)
        const internalSettingsData = await apiGet<InternalDataSettings>(`/api/v1/projects/${projectId}/internal-data/settings`).catch(() => null)
        
        if (internalSettingsData) {
          const settings = internalSettingsData.data
          setInternalData(settings)
          setInternalModeDraft(settings.source_mode || '')
          setInternalUrlDraft(settings.source_url || '')
          setInternalEnabledDraft(settings.is_enabled)
        } else {
          setInternalData(null)
          setInternalModeDraft('')
          setInternalUrlDraft('')
          setInternalEnabledDraft(false)
        }
      } catch (e: any) {
        setError(e?.detail || 'Failed to load Internal Data settings')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [projectId])

  const inferKind = (key: string): 'column' | 'attribute' => {
    const found = sourceFields.find(f => f.key === key)
    return (found?.kind as 'column' | 'attribute') || 'column'
  }

  const buildMappingJson = () => {
    const fields: any = {}

    if (skuKey) {
      const transforms: string[] = []
      if (skuStrip) transforms.push('strip')
      if (skuLastSegment) transforms.push('sku_last_segment')
      fields.internal_sku = {
        source: inferKind(skuKey),
        key: skuKey,
        transforms,
        required: true,
      }
    }

    if (rrpKey) {
      const transforms: string[] = []
      if (rrpStrip) transforms.push('strip')
      if (rrpToDecimal) transforms.push('to_decimal')
      fields.rrp = {
        source: inferKind(rrpKey),
        key: rrpKey,
        transforms,
        required: true,
      }
    }

    if (stockKey) {
      const transforms: string[] = []
      if (stockStrip) transforms.push('strip')
      if (stockToInt) transforms.push('to_int')
      fields.stock = {
        source: inferKind(stockKey),
        key: stockKey,
        transforms,
        required: false,
      }
    }

    if (barcodeKey) {
      const transforms: string[] = []
      if (barcodeStrip) transforms.push('strip')
      fields.barcode = {
        source: inferKind(barcodeKey),
        key: barcodeKey,
        transforms,
        required: false,
      }
    }

    return { fields }
  }

  const prefillMappingFromExisting = () => {
    const base = mappingDraft && mappingDraft.fields ? mappingDraft : internalData?.mapping_json ?? {}
    const fields = (base && base.fields) || {}

    const sku = fields.internal_sku || {}
    const rrp = fields.rrp || {}
    const stock = fields.stock || {}
    const barcode = fields.barcode || {}

    if (sku.key) {
      setSkuKey(sku.key)
      const transforms: string[] = sku.transforms || []
      setSkuStrip(transforms.length === 0 || transforms.includes('strip'))
      setSkuLastSegment(transforms.includes('sku_last_segment'))
    } else {
      setSkuKey('')
      setSkuStrip(true)
      setSkuLastSegment(false)
    }

    if (rrp.key) {
      setRrpKey(rrp.key)
      const transforms: string[] = rrp.transforms || []
      setRrpStrip(transforms.length === 0 || transforms.includes('strip'))
      setRrpToDecimal(transforms.length === 0 || transforms.includes('to_decimal'))
    } else {
      setRrpKey('')
      setRrpStrip(true)
      setRrpToDecimal(true)
    }

    if (stock.key) {
      setStockKey(stock.key)
      const transforms: string[] = stock.transforms || []
      setStockStrip(transforms.length === 0 || transforms.includes('strip'))
      setStockToInt(transforms.length === 0 || transforms.includes('to_int'))
    } else {
      setStockKey('')
      setStockStrip(true)
      setStockToInt(true)
    }

    if (barcode.key) {
      setBarcodeKey(barcode.key)
      const transforms: string[] = barcode.transforms || []
      setBarcodeStrip(transforms.length === 0 || transforms.includes('strip'))
    } else {
      setBarcodeKey('')
      setBarcodeStrip(true)
    }

    setMappingDraft(base || {})
  }

  /**
   * Типы ошибок загрузки полей источника
   */
  type SourceFieldsErrorType = 
    | 'url_not_tested' 
    | 'file_not_uploaded' 
    | 'source_not_found' 
    | 'source_forbidden' 
    | 'source_timeout' 
    | 'source_unavailable' 
    | 'invalid_format' 
    | 'unknown'

  /**
   * Определяет тип ошибки и возвращает понятное сообщение для пользователя
   */
  const getSourceFieldsErrorMessage = (
    errorType: SourceFieldsErrorType,
    apiError?: any
  ): string => {
    switch (errorType) {
      case 'url_not_tested':
        return 'Источник данных не проверен. Сначала нажмите «Проверить URL».'
      case 'file_not_uploaded':
        return 'Файл не загружен. Сначала загрузите файл с внутренними данными.'
      case 'source_not_found':
        return 'Файл по URL не найден (404). Проверьте ссылку.'
      case 'source_forbidden':
        return 'Нет доступа к файлу по URL. Проверьте права доступа.'
      case 'source_timeout':
        return 'Источник не отвечает. Повторите позже или проверьте доступность.'
      case 'source_unavailable':
        return 'Не удалось подключиться к источнику. Проверьте доступность.'
      case 'invalid_format':
        return 'Файл прочитан, но формат не распознан. Проверьте, что это корректный XML/CSV/XLSX.'
      case 'unknown':
      default:
        return 'Не удалось загрузить поля источника. Проверьте настройки источника данных.'
    }
  }

  /**
   * Обрезает URL для безопасного отображения (убирает токены/секреты)
   */
  const formatSourceUrl = (url: string): string => {
    try {
      const urlObj = new URL(url)
      // Показываем только домен и путь, без query params и hash
      return `${urlObj.hostname}${urlObj.pathname}`
    } catch {
      // Если невалидный URL, показываем первые 50 символов
      return url.length > 50 ? url.substring(0, 50) + '...' : url
    }
  }

  /**
   * Определяет тип ошибки на основе состояния формы и ошибки API
   */
  const detectSourceFieldsErrorType = (apiError?: any): SourceFieldsErrorType => {
    const mode = internalData?.source_mode || internalModeDraft
    
    // Тип A: URL не проверен
    if (mode === 'url') {
      const url = internalData?.source_url || internalUrlDraft
      if (!url || url.trim() === '') {
        return 'url_not_tested'
      }
      if (!internalTestResult || !internalTestResult.includes('OK')) {
        return 'url_not_tested'
      }
    }
    
    // Тип B: Файл не загружен
    if (mode === 'upload') {
      if (!internalData?.file_storage_key) {
        return 'file_not_uploaded'
      }
    }
    
    // Анализ ошибки API для детальной классификации
    if (apiError) {
      const status = apiError?.status
      const detail = apiError?.detail || ''
      const message = apiError?.message || ''
      
      // HTTP 404 - файл не найден
      if (status === 404) {
        return 'source_not_found'
      }
      
      // HTTP 401/403 - нет доступа
      if (status === 401 || status === 403) {
        return 'source_forbidden'
      }
      
      // HTTP 422/400 с признаком parsing/format ошибки
      if (status === 422 || status === 400) {
        const lowerDetail = detail.toLowerCase()
        const lowerMessage = message.toLowerCase()
        if (
          lowerDetail.includes('format') ||
          lowerDetail.includes('parse') ||
          lowerDetail.includes('invalid') ||
          lowerDetail.includes('не распознан') ||
          lowerMessage.includes('format') ||
          lowerMessage.includes('parse')
        ) {
          return 'invalid_format'
        }
      }
      
      // Timeout (HTTP 408 или специфичные сообщения)
      if (status === 408) {
        return 'source_timeout'
      }
      
      // Проверяем сообщение на признаки timeout
      const lowerMessage = message.toLowerCase()
      const lowerDetail = detail.toLowerCase()
      if (
        lowerMessage.includes('timeout') ||
        lowerMessage.includes('timed out') ||
        lowerMessage.includes('превышено время') ||
        lowerDetail.includes('timeout') ||
        lowerDetail.includes('timed out')
      ) {
        return 'source_timeout'
      }
      
      // Прочие network errors (статус 0 без timeout признаков)
      if (!status || status === 0) {
        return 'source_unavailable'
      }
      
      // Прочие клиентские ошибки (4xx)
      if (status >= 400 && status < 500) {
        return 'source_unavailable'
      }
      
      // Серверные ошибки (5xx)
      if (status >= 500) {
        return 'source_unavailable'
      }
    }
    
    // Неизвестная ошибка
    return 'unknown'
  }

  /**
   * Проверяет, готов ли источник данных для introspect
   * URL-режим: требует source_mode='url', валидный URL и успешную проверку
   * Upload-режим: требует source_mode='upload' и успешную загрузку файла
   */
  const isSourceReady = (): { ready: boolean; errorType?: SourceFieldsErrorType } => {
    const mode = internalData?.source_mode || internalModeDraft
    
    if (mode === 'url') {
      const url = internalData?.source_url || internalUrlDraft
      if (!url || url.trim() === '') {
        return { ready: false, errorType: 'url_not_tested' }
      }
      // Проверяем, что URL был успешно проверен
      if (!internalTestResult || !internalTestResult.includes('OK')) {
        return { ready: false, errorType: 'url_not_tested' }
      }
      return { ready: true }
    }
    
    if (mode === 'upload') {
      // Проверяем, что файл был успешно загружен (есть file_storage_key)
      if (!internalData?.file_storage_key) {
        return { ready: false, errorType: 'file_not_uploaded' }
      }
      return { ready: true }
    }
    
    return { ready: false, errorType: 'unknown' }
  }

  /**
   * Загружает поля источника ТОЛЬКО если источник готов
   */
  const loadSourceFields = async (): Promise<boolean> => {
    const { ready, errorType } = isSourceReady()
    
    if (!ready) {
      // Источник не готов - определяем тип ошибки и показываем понятное сообщение
      const errorTypeDetected = errorType || detectSourceFieldsErrorType()
      const errorMsg = getSourceFieldsErrorMessage(errorTypeDetected)
      setSourceFieldsError(errorMsg)
      setSourceFieldsErrorType(errorTypeDetected)
      setSourceFields([])
      setSourceFieldsSampleRows([])
      
      const mode = internalData?.source_mode || internalModeDraft
      const url = internalData?.source_url || internalUrlDraft
      const urlDisplay = url ? formatSourceUrl(url) : null
      
      console.log('[loadSourceFields] Источник не готов:', {
        source_mode: mode,
        url: urlDisplay,
        errorType: errorTypeDetected
      })
      return false
    }

    try {
      setSourceFieldsLoading(true)
      setSourceFieldsError(null)
      setSourceFieldsErrorType(null)
      setSourceFieldsSampleRows([])
      
      const { data } = await apiPost<{
        file_format: string | null
        source_fields: InternalDataSourceField[]
        sample_rows: any[]
      }>(`/api/v1/projects/${projectId}/internal-data/introspect`, {})
      
      setSourceFields(data.source_fields || [])
      setSourceFieldsSampleRows(data.sample_rows || [])
      prefillMappingFromExisting()
      return true
    } catch (e: any) {
      // Определяем тип ошибки на основе ответа API
      const errorTypeDetected = detectSourceFieldsErrorType(e)
      const errorMsg = getSourceFieldsErrorMessage(errorTypeDetected, e)
      
      // Получаем контекст для диагностики
      const mode = internalData?.source_mode || internalModeDraft
      const url = internalData?.source_url || internalUrlDraft
      const urlDisplay = url ? formatSourceUrl(url) : null
      
      // Логируем реальную ошибку в консоль для разработчиков
      console.error('[loadSourceFields] Introspect error:', {
        source_mode: mode,
        url: urlDisplay,
        http_status: e?.status,
        errorType: errorTypeDetected,
        detail: e?.detail,
        message: e?.message,
        error_payload: e?.parsed || e?.debug?.parsed,
        error: e
      })
      
      setSourceFieldsError(errorMsg)
      setSourceFieldsErrorType(errorTypeDetected)
      setSourceFields([])
      
      // Если есть sample_rows в ответе (даже при ошибке), сохраняем их
      if (e?.parsed?.sample_rows) {
        setSourceFieldsSampleRows(e.parsed.sample_rows)
      } else if (e?.debug?.parsed?.sample_rows) {
        setSourceFieldsSampleRows(e.debug.parsed.sample_rows)
      }
      
      // НЕ устанавливаем internalError, чтобы не блокировать форму
      return false
    } finally {
      setSourceFieldsLoading(false)
    }
  }

  useEffect(() => {
    if (!showMappingWizard) return
    
    // При открытии модального окна проверяем готовность источника
    // и загружаем поля ТОЛЬКО если источник готов
    const { ready } = isSourceReady()
    if (ready) {
      loadSourceFields()
    } else {
      // Очищаем поля, если источник не готов
      const { errorType } = isSourceReady()
      const errorTypeDetected = errorType || detectSourceFieldsErrorType()
      const errorMsg = getSourceFieldsErrorMessage(errorTypeDetected)
      setSourceFields([])
      setSourceFieldsError(errorMsg)
      setSourceFieldsErrorType(errorTypeDetected)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showMappingWizard, projectId])

  const saveInternalSettings = async () => {
    try {
      setInternalLoading(true)
      setInternalError(null)
      setInternalTestResult(null)
      const mode = internalModeDraft || null
      const payload: any = {
        is_enabled: internalEnabledDraft,
        source_mode: mode,
        source_url: mode === 'url' ? internalUrlDraft : null,
        file_format: internalData?.file_format || null,
        mapping_json: internalData?.mapping_json ?? {},
      }
      const { data } = await apiPut<InternalDataSettings>(`/api/v1/projects/${projectId}/internal-data/settings`, payload)
      setInternalData(data)
      setInternalModeDraft(data.source_mode || '')
      setInternalUrlDraft(data.source_url || '')
      setInternalEnabledDraft(data.is_enabled)
      setToast('Настройки сохранены')
      setTimeout(() => setToast(null), 3000)
      
      // Если источник настроен и готов, загружаем поля
      // Но только если это действительно готовый источник (не просто сохранённый режим)
      // И только если Internal Data включен
      if (data.is_enabled) {
        const { ready, errorType } = isSourceReady()
        if (ready) {
          await loadSourceFields()
        } else {
          // Очищаем поля, если источник не готов после сохранения
          const errorTypeDetected = errorType || detectSourceFieldsErrorType()
          const errorMsg = getSourceFieldsErrorMessage(errorTypeDetected)
          setSourceFields([])
          setSourceFieldsError(errorMsg)
          setSourceFieldsErrorType(errorTypeDetected)
        }
      } else {
        // Если Internal Data выключен, очищаем поля
        setSourceFields([])
        setSourceFieldsError(null)
        setSourceFieldsErrorType(null)
      }
    } catch (e: any) {
      setInternalError(e?.detail || 'Failed to save Internal Data settings')
    } finally {
      setInternalLoading(false)
    }
  }

  const checkInternalUrl = async () => {
    try {
      setInternalTesting(true)
      setInternalTestResult(null)
      const payload: any = {
        url: internalModeDraft === 'url' ? internalUrlDraft : null,
      }
      const { data } = await apiPost<{
        ok: boolean
        http_status: number | null
        error: string | null
      }>(`/api/v1/projects/${projectId}/internal-data/test-url`, payload)
      if (data.ok) {
        setInternalTestResult(`URL OK (status ${data.http_status ?? 200})`)
        // После успешной проверки URL загружаем поля источника
        // Теперь источник готов, можно вызывать introspect
        await loadSourceFields()
      } else {
        setInternalTestResult(data.error || 'URL test failed')
        setSourceFields([])
        setSourceFieldsError('Источник данных не проверен. Сначала нажмите «Проверить URL».')
        setSourceFieldsErrorType('url_not_tested')
      }
    } catch (e: any) {
      // #region agent log
      try {
        fetch('http://127.0.0.1:7242/ingest/66ddcc6b-d2d0-4156-a371-04fea067f11b',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'page.tsx:292','message':'checkInternalUrl error','data':{error:e?.message||String(e),detail:e?.detail},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'H5'})}).catch(()=>{});
      } catch {}
      // #endregion
      setInternalTestResult(e?.detail || 'URL test failed')
      setSourceFields([])
      setSourceFieldsError('Источник данных не проверен. Сначала нажмите «Проверить URL».')
      setSourceFieldsErrorType('url_not_tested')
    } finally {
      setInternalTesting(false)
    }
  }

  const syncInternalData = async () => {
    try {
      setInternalSyncing(true)
      setSyncResult(null)
      setShowSyncErrors(false)
      const { data } = await apiPost<{
        status: string
        snapshot_id: number | null
        row_count: number | null
        rows_total: number | null
        rows_imported: number | null
        rows_failed: number | null
        errors_preview: Array<{ row_index: number; message: string; source_key?: string }> | null
        error: string | null
      }>(`/api/v1/projects/${projectId}/internal-data/sync`, {})
      
      if (data.status === 'success' || data.status === 'partial') {
        const total = data.rows_total ?? 0
        const imported = data.rows_imported ?? data.row_count ?? 0
        const failed = data.rows_failed ?? 0
        
        if (failed > 0) {
          setSyncResult({
            snapshot_id: data.snapshot_id,
            rows_total: total,
            rows_imported: imported,
            rows_failed: failed,
            errors_preview: data.errors_preview || null,
          })
          setToast(`Загружено ${imported} строк, пропущено ${failed} (ошибки в данных)`)
        } else {
          setToast(`Internal Data synced (${imported} rows)`)
        }
      } else {
        setToast(`Internal Data sync error: ${data.error || 'unknown error'}`)
      }
      setTimeout(() => setToast(null), 4000)

      try {
        const { data: settings } = await apiGet<InternalDataSettings>(`/api/v1/projects/${projectId}/internal-data/settings`)
        setInternalData(settings)
        setInternalModeDraft(settings.source_mode || '')
        setInternalUrlDraft(settings.source_url || '')
        setInternalEnabledDraft(settings.is_enabled)
      } catch {
        // ignore
      }
    } catch (e: any) {
      setToast(e?.detail || 'Internal Data sync failed')
      setTimeout(() => setToast(null), 4000)
    } finally {
      setInternalSyncing(false)
    }
  }

  const handleInternalFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      setInternalUploading(true)
      setInternalError(null)
      const formData = new FormData()
      formData.append('file', file)
      const apiBase = getApiBase()
      const token = getAccessToken()
      const res = await fetch(`${apiBase}/api/v1/projects/${projectId}/internal-data/upload`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        body: formData,
      })
      const raw = await res.json()
      if (!res.ok) {
        throw raw
      }
      const settings = raw.settings as InternalDataSettings
      setInternalData(settings)
      setInternalModeDraft(settings.source_mode || 'upload')
      setInternalEnabledDraft(settings.is_enabled)
      // Keep selectedFile state - don't reset it
      setToast('Internal Data file uploaded')
      setTimeout(() => setToast(null), 3000)

      // После успешной загрузки файла источник готов, можно вызывать introspect
      await loadSourceFields()
      
      // If mapping is effectively missing (no fields.internal_sku/rrp), open mapping wizard.
      const mapping = settings.mapping_json ?? {}
      const fields = mapping.fields || {}
      const hasSku = fields.internal_sku && fields.internal_sku.key
      const hasRrp = fields.rrp && fields.rrp.key
      if (!hasSku || !hasRrp) {
        setMappingDraft(mapping || {})
        setShowMappingWizard(true)
      }
    } catch (e: any) {
      setInternalError(e?.detail || 'Failed to upload Internal Data file')
      setSelectedFile(null)
    } finally {
      setInternalUploading(false)
      // Don't reset input value - let user see selected file
    }
  }

  const openMappingWizard = () => {
    const mapping = internalData?.mapping_json ?? {}
    setMappingDraft(mapping || {})
    setShowMappingWizard(true)
  }

  const handleValidateMapping = async () => {
    try {
      setMappingLoading(true)
      setMappingPreview(null)
      const mapping_json = buildMappingJson()
      setMappingDraft(mapping_json)
      const { data } = await apiPost<{
        preview_rows: any[]
        errors: { row_index: number; message: string }[]
      }>(`/api/v1/projects/${projectId}/internal-data/validate-mapping`, {
        mapping_json,
      })
      setMappingPreview({ rows: data.preview_rows, errors: data.errors })
    } catch (e: any) {
      setMappingPreview({
        rows: [],
        errors: [{ row_index: -1, message: e?.detail || 'Failed to validate mapping' }],
      })
    } finally {
      setMappingLoading(false)
    }
  }

  const handleSaveMapping = async () => {
    if (!internalData) return
    try {
      setMappingLoading(true)
      const mapping_json = buildMappingJson()
      setMappingDraft(mapping_json)
      const payload: any = {
        is_enabled: internalEnabledDraft,
        source_mode: internalModeDraft || null,
        source_url: internalModeDraft === 'url' ? internalUrlDraft : null,
        file_format: internalData.file_format || null,
        mapping_json,
      }
      const { data } = await apiPut<InternalDataSettings>(`/api/v1/projects/${projectId}/internal-data/settings`, payload)
      setInternalData(data)
      setInternalModeDraft(data.source_mode || '')
      setInternalUrlDraft(data.source_url || '')
      setInternalEnabledDraft(data.is_enabled)
      setShowMappingWizard(false)
      setToast('Mapping saved')
      setTimeout(() => setToast(null), 3000)
    } catch (e: any) {
      console.error('Failed to save mapping', e)
      const detail =
        e?.detail ||
        e?.debug?.bodyPreview ||
        e?.message ||
        (typeof e === 'string' ? e : '')
      setInternalError(detail ? `Failed to save mapping: ${detail}` : 'Failed to save mapping')
    } finally {
      setMappingLoading(false)
    }
  }

  const mappingRequiredSelected = !!skuKey && !!rrpKey

  // Единый базовый стиль для всех кнопок в секциях "Структура данных" и "Ручные действия"
  const uniformButtonBaseStyle: React.CSSProperties = {
    height: '44px',
    padding: '0 24px', // px-6 эквивалент
    minWidth: '220px',
    fontSize: '0.875rem', // text-sm
    lineHeight: '1', // leading-none
    borderRadius: '4px',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    whiteSpace: 'nowrap',
    fontWeight: 500,
  }

  return (
    <div className="container">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <h1>Загрузка каталога</h1>
        <Link href={`/app/project/${projectId}/settings`}>← Назад к настройкам</Link>
      </div>

      {toast && <div className="toast">{toast}</div>}

      {loading ? (
        <p>Loading...</p>
      ) : error ? (
        <div className="card">
          <p style={{ color: 'crimson' }}>{error}</p>
        </div>
      ) : (
        <div className="card" style={{ padding: '20px' }}>
          {/* [1] Статус - всегда виден */}
          <div style={{ marginBottom: '20px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '10px' }}>
              <div style={{ fontSize: '0.9rem', color: '#555', flex: 1 }}>
                <div style={{ marginBottom: '4px' }}>
                  Статус:{' '}
                  <strong>
                    {internalData?.is_enabled ? 'Включено' : 'Выключено'}
                  </strong>
                </div>
                <div style={{ marginBottom: '4px' }}>
                  Последняя проверка:{' '}
                  {internalData?.last_test_at
                    ? `${new Date(internalData.last_test_at).toLocaleString()}`
                    : 'никогда'}
                </div>
                <div style={{ marginBottom: '4px' }}>
                  Последняя синхронизация:{' '}
                  {internalData?.last_sync_at
                    ? `${new Date(internalData.last_sync_at).toLocaleString()}`
                    : 'никогда'}
                </div>
                {internalData?.last_sync_error && (
                  <div style={{ color: 'crimson', marginTop: '4px' }}>
                    Ошибка синхронизации: {internalData.last_sync_error}
                  </div>
                )}
              </div>
              <Link
                href={`/app/project/${projectId}/ingestion`}
                style={{
                  fontSize: '0.9rem',
                  color: '#2563eb',
                  textDecoration: 'none',
                  marginLeft: '16px',
                  whiteSpace: 'nowrap',
                }}
              >
                Логи и расписание →
              </Link>
            </div>

            <div>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <input
                  type="checkbox"
                  checked={internalEnabledDraft}
                  onChange={e => setInternalEnabledDraft(e.target.checked)}
                />
                <span>Включить загрузку каталога для этого проекта</span>
              </label>
            </div>
          </div>

          {/* [2] Настройки источника - показывать только если чекбокс включен */}
          {internalEnabledDraft && (
            <div data-source-block style={{ marginBottom: '20px', paddingTop: '20px', borderTop: '1px solid #e0e0e0' }}>
              <h3 style={{ marginTop: 0, marginBottom: '12px', fontSize: '1.1rem' }}>Настройки источника</h3>
              
              <div style={{ marginBottom: '12px' }}>
                <label style={{ marginRight: '12px' }}>
                  <input
                    type="radio"
                    name="internal-source-mode"
                    value="url"
                    checked={internalModeDraft === 'url'}
                    onChange={() => {
                      setInternalModeDraft('url')
                      setSelectedFile(null)
                    }}
                  />{' '}
                  URL
                </label>
                <label>
                  <input
                    type="radio"
                    name="internal-source-mode"
                    value="upload"
                    checked={internalModeDraft === 'upload'}
                    onChange={() => {
                      setInternalModeDraft('upload')
                      setSelectedFile(null)
                    }}
                  />{' '}
                  Загрузить с компьютера
                </label>
              </div>

              {internalModeDraft === 'url' && (
                <div style={{ marginBottom: '12px' }}>
                  <label style={{ display: 'block', marginBottom: '4px' }}>URL файла с внутренними данными</label>
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'flex-start', flexWrap: 'wrap' }}>
                    <input
                      type="text"
                      style={{ flex: 1, minWidth: '300px', padding: '6px 8px', boxSizing: 'border-box' }}
                      value={internalUrlDraft}
                      onChange={e => setInternalUrlDraft(e.target.value)}
                      placeholder="https://example.com/internal-data.csv"
                    />
                    <button
                      onClick={checkInternalUrl}
                      disabled={internalTesting || !internalEnabledDraft}
                      type="button"
                      style={{
                        padding: '6px 12px',
                        backgroundColor: internalTesting || !internalEnabledDraft ? '#f5f5f5' : '#fff',
                        border: '1px solid #ccc',
                        borderRadius: '4px',
                        cursor: internalTesting || !internalEnabledDraft ? 'not-allowed' : 'pointer',
                        whiteSpace: 'nowrap',
                        flexShrink: 0,
                        color: internalTesting || !internalEnabledDraft ? '#999' : '#333',
                      }}
                    >
                      {internalTesting ? 'Проверка...' : 'Проверить URL'}
                    </button>
                  </div>
                  {internalTestResult && (
                    <div style={{ marginTop: '6px', fontSize: '0.9rem' }}>{internalTestResult}</div>
                  )}
                </div>
              )}

              {internalModeDraft === 'upload' && (
                <div data-upload-block style={{ marginBottom: '12px' }}>
                  <label style={{ display: 'block', marginBottom: '4px' }}>
                    Загрузить файл (CSV/XLSX/XML) с внутренними данными
                  </label>
                  <input 
                    type="file" 
                    accept=".csv,.xlsx,.xml" 
                    onChange={(e) => {
                      const file = e.target.files?.[0] || null
                      setSelectedFile(file)
                      if (file) {
                        handleInternalFileChange(e)
                      } else {
                        setSelectedFile(null)
                      }
                    }}
                  />
                  <div style={{ marginTop: '6px', fontSize: '0.9rem', color: '#555' }}>
                    {selectedFile ? (
                      <>Выбран файл: <strong>{selectedFile.name}</strong></>
                    ) : (
                      <>Файл не выбран</>
                    )}
                  </div>
                </div>
              )}

              {internalError && (
                <div style={{ marginTop: '8px', color: 'crimson', fontSize: '0.9rem' }}>{internalError}</div>
              )}
            </div>
          )}

          {/* [3] Структура данных - показывать только если чекбокс включен */}
          {internalEnabledDraft && (
            <div style={{ marginBottom: '20px', paddingTop: '20px', borderTop: '1px solid #e0e0e0' }}>
              <h3 style={{ marginTop: 0, marginBottom: '12px', fontSize: '1.1rem' }}>Структура данных</h3>
              <div style={{ display: 'flex', gap: '12px', flexWrap: 'nowrap', alignItems: 'stretch' }}>
                <button
                  onClick={openMappingWizard}
                  disabled={!internalData}
                  style={{
                    ...uniformButtonBaseStyle,
                    backgroundColor: '#6c757d',
                    color: 'white',
                    border: 'none',
                    cursor: !internalData ? 'not-allowed' : 'pointer',
                  }}
                >
                  Сопоставление полей
                </button>
                <Link
                  href={`/app/project/${projectId}/internal-data/categories`}
                  style={{
                    ...uniformButtonBaseStyle,
                    backgroundColor: '#6c757d',
                    color: 'white',
                    textDecoration: 'none',
                    border: 'none',
                  }}
                >
                  Настройка категорий
                </Link>
              </div>
            </div>
          )}

          {/* [4] Ручные действия - показывать только если чекбокс включен */}
          {internalEnabledDraft && (
            <div style={{ marginBottom: '20px', paddingTop: '20px', borderTop: '1px solid #e0e0e0' }}>
              <h3 style={{ marginTop: 0, marginBottom: '12px', fontSize: '1.1rem' }}>Ручные действия</h3>
              <div style={{ marginBottom: '8px' }}>
                <button
                  onClick={() => {
                    const mapping = internalData?.mapping_json ?? {}
                    const fields = mapping.fields || {}
                    const hasSku = fields.internal_sku && fields.internal_sku.key
                    const hasRrp = fields.rrp && fields.rrp.key
                    if (!hasSku || !hasRrp) {
                      openMappingWizard()
                      return
                    }
                    syncInternalData()
                  }}
                  disabled={
                    internalSyncing ||
                    !internalEnabledDraft ||
                    !internalModeDraft ||
                    (internalModeDraft === 'url' && !internalUrlDraft)
                  }
                  style={{
                    ...uniformButtonBaseStyle,
                    backgroundColor: '#28a745',
                    color: 'white',
                    border: 'none',
                    cursor: (internalSyncing ||
                      !internalEnabledDraft ||
                      !internalModeDraft ||
                      (internalModeDraft === 'url' && !internalUrlDraft)) ? 'not-allowed' : 'pointer',
                  }}
                >
                  {internalSyncing ? 'Синхронизация...' : 'Синхронизировать сейчас'}
                </button>
              </div>
              <div style={{ fontSize: '0.85rem', color: '#666', marginTop: '4px' }}>
                Запускает импорт вручную, независимо от расписания.
              </div>

              {syncResult && syncResult.rows_failed && syncResult.rows_failed > 0 && (
                <div style={{ marginTop: '12px', padding: '12px', backgroundColor: '#fff3cd', border: '1px solid #ffc107', borderRadius: '4px' }}>
                  <div style={{ marginBottom: '8px' }}>
                    <strong>
                      Импортировано {syncResult.rows_imported ?? 0} / Всего {syncResult.rows_total ?? 0} / Ошибок {syncResult.rows_failed}
                    </strong>
                  </div>
                  <div style={{ marginTop: '8px' }}>
                    {!showSyncErrors ? (
                      <button
                        onClick={async () => {
                          if (syncResult.snapshot_id) {
                            setSyncErrorsLoading(true)
                            try {
                              const { data } = await apiGet<{
                                total: number
                                items: Array<{
                                  id: number
                                  row_index: number
                                  source_key: string | null
                                  raw_row: any
                                  error_code: string | null
                                  message: string
                                  transforms: string[] | null
                                  trace: any
                                  created_at: string
                                }>
                              }>(`/api/v1/projects/${projectId}/internal-data/snapshots/${syncResult.snapshot_id}/errors?limit=100&offset=0`)
                              setSyncErrorsData(data)
                              setShowSyncErrors(true)
                            } catch (e: any) {
                              setInternalError(e?.detail || 'Failed to load errors')
                            } finally {
                              setSyncErrorsLoading(false)
                            }
                          }
                        }}
                        style={{ fontSize: '0.9rem', padding: '4px 8px' }}
                        disabled={syncErrorsLoading}
                      >
                        {syncErrorsLoading ? 'Загрузка...' : 'Посмотреть ошибки'}
                      </button>
                    ) : (
                      <div>
                        <button
                          onClick={() => {
                            setShowSyncErrors(false)
                            setSyncErrorsData(null)
                            setSyncErrorsOffset(0)
                          }}
                          style={{ fontSize: '0.9rem', padding: '4px 8px', marginBottom: '8px' }}
                        >
                          Скрыть ошибки
                        </button>
                        {syncErrorsData && (
                          <div style={{ marginTop: '8px', fontSize: '0.85rem' }}>
                            <div style={{ marginBottom: '8px', color: '#666' }}>
                              Всего ошибок: {syncErrorsData.total}
                            </div>
                            <div style={{ maxHeight: '400px', overflowY: 'auto', border: '1px solid #ddd', borderRadius: '4px', padding: '8px' }}>
                              {syncErrorsData.items.map((err) => (
                                <div key={err.id} style={{ marginBottom: '8px', padding: '8px', backgroundColor: '#fff', borderRadius: '2px', border: '1px solid #eee' }}>
                                  <div style={{ fontWeight: 600, marginBottom: '4px' }}>
                                    Строка {err.row_index}: {err.message}
                                  </div>
                                  {err.source_key && (
                                    <div style={{ color: '#666', fontSize: '0.85rem', marginBottom: '2px' }}>
                                      Поле: {err.source_key}
                                    </div>
                                  )}
                                  {err.error_code && (
                                    <div style={{ color: '#666', fontSize: '0.85rem', marginBottom: '2px' }}>
                                      Код ошибки: {err.error_code}
                                    </div>
                                  )}
                                  {err.raw_row && (
                                    <details style={{ marginTop: '4px' }}>
                                      <summary style={{ cursor: 'pointer', color: '#2563eb', fontSize: '0.85rem' }}>
                                        Сырые данные
                                      </summary>
                                      <pre style={{ marginTop: '4px', padding: '4px', backgroundColor: '#f5f5f5', borderRadius: '2px', fontSize: '0.75rem', overflow: 'auto' }}>
                                        {JSON.stringify(err.raw_row, null, 2)}
                                      </pre>
                                    </details>
                                  )}
                                </div>
                              ))}
                            </div>
                            {syncErrorsData.total > syncErrorsData.items.length && (
                              <div style={{ marginTop: '8px', fontSize: '0.85rem', color: '#666' }}>
                                Показано {syncErrorsData.items.length} из {syncErrorsData.total} ошибок
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* [5] СОХРАНЕНИЕ - всегда видно */}
          <div style={{ paddingTop: '20px', borderTop: '1px solid #e0e0e0' }}>
            <button
              onClick={saveInternalSettings}
              disabled={internalLoading || internalUploading}
              style={{
                ...uniformButtonBaseStyle,
                backgroundColor: '#0d6efd',
                color: 'white',
                border: 'none',
                cursor: internalLoading || internalUploading ? 'not-allowed' : 'pointer',
              }}
            >
              {internalUploading
                ? 'Загрузка...'
                : internalLoading
                ? 'Сохранение...'
                : 'Сохранить настройки'}
            </button>
          </div>
        </div>
      )}

      {showMappingWizard && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0,0,0,0.5)',
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            zIndex: 1000,
          }}
        >
          <div style={{ backgroundColor: 'white', padding: 20, borderRadius: 4, maxWidth: 900, width: '100%' }}>
            <h3 style={{ marginTop: 0 }}>Mapping Internal Data</h3>
            <p style={{ fontSize: '0.9rem', color: '#555', marginBottom: 24 }}>
              Выберите поля источника для внутренних полей. Минимум: Internal SKU и RRP.
            </p>
            
            {sourceFieldsLoading && (
              <div style={{ marginBottom: 16, padding: '8px 12px', backgroundColor: '#e7f3ff', border: '1px solid #b3d9ff', borderRadius: '4px', fontSize: '0.9rem' }}>
                Загрузка полей источника...
              </div>
            )}
            
            {sourceFieldsError && !sourceFieldsLoading && (() => {
              const mode = internalData?.source_mode || internalModeDraft
              const url = internalData?.source_url || internalUrlDraft
              const urlDisplay = url ? formatSourceUrl(url) : null
              const sourceContext = mode === 'url' 
                ? `Источник: URL (${urlDisplay || 'не указан'})`
                : 'Источник: Upload'
              
              return (
                <div style={{ marginBottom: 16, padding: '12px', backgroundColor: '#ffe7e7', border: '1px solid #ffb3b3', borderRadius: '4px', fontSize: '0.9rem' }}>
                  <div style={{ color: '#c00', marginBottom: 8, fontWeight: 500 }}>
                    {sourceFieldsError}
                  </div>
                  <div style={{ color: '#666', fontSize: '0.85rem', marginBottom: 12 }}>
                    {sourceContext}
                  </div>
                  
                  {/* Кнопки действий */}
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 12 }}>
                    {mode === 'url' && (
                      <>
                        <button
                          onClick={async () => {
                            await checkInternalUrl()
                          }}
                          disabled={internalTesting}
                          style={{
                            padding: '6px 12px',
                            backgroundColor: '#0d6efd',
                            color: 'white',
                            border: 'none',
                            borderRadius: '4px',
                            fontSize: '0.9rem',
                            cursor: internalTesting ? 'not-allowed' : 'pointer',
                          }}
                        >
                          {internalTesting ? 'Проверка...' : 'Проверить URL'}
                        </button>
                        <button
                          onClick={() => {
                            setShowMappingWizard(false)
                            // Скроллим к блоку источника
                            setTimeout(() => {
                              const sourceBlock = document.querySelector('[data-source-block]')
                              if (sourceBlock) {
                                sourceBlock.scrollIntoView({ behavior: 'smooth', block: 'start' })
                              }
                            }, 100)
                          }}
                          style={{
                            padding: '6px 12px',
                            backgroundColor: 'transparent',
                            color: '#0d6efd',
                            border: '1px solid #0d6efd',
                            borderRadius: '4px',
                            fontSize: '0.9rem',
                            cursor: 'pointer',
                          }}
                        >
                          Открыть настройки источника
                        </button>
                        <button
                          onClick={() => loadSourceFields()}
                          disabled={sourceFieldsLoading}
                          style={{
                            padding: '6px 12px',
                            backgroundColor: 'transparent',
                            color: '#666',
                            border: '1px solid #ccc',
                            borderRadius: '4px',
                            fontSize: '0.9rem',
                            cursor: sourceFieldsLoading ? 'not-allowed' : 'pointer',
                          }}
                        >
                          Повторить загрузку полей
                        </button>
                      </>
                    )}
                    
                    {mode === 'upload' && (
                      <>
                        <button
                          onClick={() => {
                            setShowMappingWizard(false)
                            // Скроллим к блоку upload
                            setTimeout(() => {
                              const uploadBlock = document.querySelector('[data-upload-block]')
                              if (uploadBlock) {
                                uploadBlock.scrollIntoView({ behavior: 'smooth', block: 'start' })
                              }
                            }, 100)
                          }}
                          style={{
                            padding: '6px 12px',
                            backgroundColor: '#0d6efd',
                            color: 'white',
                            border: 'none',
                            borderRadius: '4px',
                            fontSize: '0.9rem',
                            cursor: 'pointer',
                          }}
                        >
                          Открыть настройки источника
                        </button>
                        <button
                          onClick={() => loadSourceFields()}
                          disabled={sourceFieldsLoading}
                          style={{
                            padding: '6px 12px',
                            backgroundColor: 'transparent',
                            color: '#666',
                            border: '1px solid #ccc',
                            borderRadius: '4px',
                            fontSize: '0.9rem',
                            cursor: sourceFieldsLoading ? 'not-allowed' : 'pointer',
                          }}
                        >
                          Повторить загрузку полей
                        </button>
                      </>
                    )}
                    
                    {sourceFieldsErrorType === 'invalid_format' && sourceFieldsSampleRows.length > 0 && (
                      <button
                        onClick={() => setShowSampleRows(!showSampleRows)}
                        style={{
                          padding: '6px 12px',
                          backgroundColor: 'transparent',
                          color: '#666',
                          border: '1px solid #ccc',
                          borderRadius: '4px',
                          fontSize: '0.9rem',
                          cursor: 'pointer',
                        }}
                      >
                        {showSampleRows ? 'Скрыть пример' : 'Показать пример полей (sample)'}
                      </button>
                    )}
                  </div>
                  
                  {/* Показ sample rows при invalid_format */}
                  {sourceFieldsErrorType === 'invalid_format' && showSampleRows && sourceFieldsSampleRows.length > 0 && (
                    <div style={{ marginTop: 12, padding: '12px', backgroundColor: '#f8f9fa', border: '1px solid #e0e0e0', borderRadius: '4px' }}>
                      <div style={{ fontSize: '0.85rem', fontWeight: 500, marginBottom: 8, color: '#555' }}>
                        Пример данных из файла (первые строки):
                      </div>
                      <pre style={{ 
                        fontSize: '0.8rem', 
                        overflow: 'auto', 
                        maxHeight: '200px',
                        padding: '8px',
                        backgroundColor: '#fff',
                        border: '1px solid #ddd',
                        borderRadius: '2px'
                      }}>
                        {JSON.stringify(sourceFieldsSampleRows, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              )
            })()}
            
            {!sourceFieldsLoading && !sourceFieldsError && sourceFields.length === 0 && (() => {
              const { ready, errorType } = isSourceReady()
              if (!ready) {
                const mode = internalData?.source_mode || internalModeDraft
                if (mode === 'url') {
                  return (
                    <div style={{ marginBottom: 16, padding: '8px 12px', backgroundColor: '#fff3cd', border: '1px solid #ffc107', borderRadius: '4px', fontSize: '0.9rem' }}>
                      Сначала проверьте источник данных (URL)
                    </div>
                  )
                } else if (mode === 'upload') {
                  return (
                    <div style={{ marginBottom: 16, padding: '8px 12px', backgroundColor: '#fff3cd', border: '1px solid #ffc107', borderRadius: '4px', fontSize: '0.9rem' }}>
                      Сначала загрузите файл
                    </div>
                  )
                }
              }
              return null
            })()}

            {/* Field Block: Internal SKU */}
            <div style={{ marginBottom: 32 }}>
              <div style={{ marginBottom: 8 }}>
                <div style={{ fontWeight: 600, fontSize: '1rem' }}>
                  Internal SKU<span style={{ color: 'crimson' }}> *</span>
                </div>
                <div style={{ fontSize: '0.85rem', color: '#666', marginTop: 4 }}>
                  Используется как уникальный идентификатор товара. Изменение значения приведёт к созданию нового товара.
                </div>
              </div>
              <div style={{ marginBottom: 12 }}>
                <select
                  style={{ width: '100%', padding: '6px 8px', boxSizing: 'border-box' }}
                  value={skuKey}
                  onChange={e => setSkuKey(e.target.value)}
                  disabled={sourceFieldsLoading || sourceFields.length === 0}
                >
                  <option value="">
                    {sourceFieldsLoading 
                      ? 'Загрузка полей...' 
                      : sourceFields.length === 0 
                        ? (() => {
                            const { ready } = isSourceReady()
                            if (!ready) {
                              const mode = internalData?.source_mode || internalModeDraft
                              return mode === 'url' ? 'Сначала проверьте источник данных' : 'Сначала загрузите файл'
                            }
                            return 'Источник данных недоступен'
                          })()
                        : '— не выбрано —'}
                  </option>
                  {sourceFields.map(f => (
                    <option key={f.key} value={f.key}>
                      {f.label}
                    </option>
                  ))}
                </select>
              </div>
              <div style={{ 
                marginTop: 12, 
                padding: '12px', 
                backgroundColor: '#f8f9fa', 
                border: '1px solid #e0e0e0', 
                borderRadius: '4px' 
              }}>
                <div style={{ fontSize: '0.9rem', fontWeight: 500, marginBottom: 8, color: '#555' }}>
                  Обработка значения
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '8px 12px', alignItems: 'center' }}>
                  <div>
                    <input
                      type="checkbox"
                      checked={skuStrip}
                      onChange={e => setSkuStrip(e.target.checked)}
                    />
                  </div>
                  <div style={{ fontSize: '0.9rem', color: '#333' }}>
                    Удалить пробелы в начале и конце строки
                  </div>
                  <div>
                    <input
                      type="checkbox"
                      checked={skuLastSegment}
                      onChange={e => setSkuLastSegment(e.target.checked)}
                    />
                  </div>
                  <div style={{ fontSize: '0.9rem', color: '#333' }}>
                    Использовать последний сегмент после разделителя
                  </div>
                </div>
              </div>
            </div>

            {/* Field Block: RRP */}
            <div style={{ marginBottom: 32 }}>
              <div style={{ marginBottom: 8 }}>
                <div style={{ fontWeight: 600, fontSize: '1rem' }}>
                  RRP<span style={{ color: 'crimson' }}> *</span>
                </div>
              </div>
              <div style={{ marginBottom: 12 }}>
                <select
                  style={{ width: '100%', padding: '6px 8px', boxSizing: 'border-box' }}
                  value={rrpKey}
                  onChange={e => setRrpKey(e.target.value)}
                  disabled={sourceFieldsLoading || sourceFields.length === 0}
                >
                  <option value="">
                    {sourceFieldsLoading 
                      ? 'Загрузка полей...' 
                      : sourceFields.length === 0 
                        ? (() => {
                            const { ready } = isSourceReady()
                            if (!ready) {
                              const mode = internalData?.source_mode || internalModeDraft
                              return mode === 'url' ? 'Сначала проверьте источник данных' : 'Сначала загрузите файл'
                            }
                            return 'Источник данных недоступен'
                          })()
                        : '— не выбрано —'}
                  </option>
                  {sourceFields.map(f => (
                    <option key={f.key} value={f.key}>
                      {f.label}
                    </option>
                  ))}
                </select>
              </div>
              <div style={{ 
                marginTop: 12, 
                padding: '12px', 
                backgroundColor: '#f8f9fa', 
                border: '1px solid #e0e0e0', 
                borderRadius: '4px' 
              }}>
                <div style={{ fontSize: '0.9rem', fontWeight: 500, marginBottom: 8, color: '#555' }}>
                  Обработка значения
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '8px 12px', alignItems: 'center' }}>
                  <div>
                    <input
                      type="checkbox"
                      checked={rrpStrip}
                      onChange={e => setRrpStrip(e.target.checked)}
                    />
                  </div>
                  <div style={{ fontSize: '0.9rem', color: '#333' }}>
                    Удалить пробелы в начале и конце строки
                  </div>
                  <div>
                    <input
                      type="checkbox"
                      checked={rrpToDecimal}
                      onChange={e => setRrpToDecimal(e.target.checked)}
                    />
                  </div>
                  <div style={{ fontSize: '0.9rem', color: '#333' }}>
                    Преобразовать в десятичное число
                  </div>
                </div>
              </div>
            </div>

            {/* Field Block: Stock */}
            <div style={{ marginBottom: 32 }}>
              <div style={{ marginBottom: 8 }}>
                <div style={{ fontWeight: 600, fontSize: '1rem' }}>
                  Stock (optional)
                </div>
              </div>
              <div style={{ marginBottom: 12 }}>
                <select
                  style={{ width: '100%', padding: '6px 8px', boxSizing: 'border-box' }}
                  value={stockKey}
                  onChange={e => setStockKey(e.target.value)}
                  disabled={sourceFieldsLoading || sourceFields.length === 0}
                >
                  <option value="">
                    {sourceFieldsLoading 
                      ? 'Загрузка полей...' 
                      : sourceFields.length === 0 
                        ? (() => {
                            const { ready } = isSourceReady()
                            if (!ready) {
                              const mode = internalData?.source_mode || internalModeDraft
                              return mode === 'url' ? 'Сначала проверьте источник данных' : 'Сначала загрузите файл'
                            }
                            return 'Источник данных недоступен'
                          })()
                        : '— не выбрано —'}
                  </option>
                  {sourceFields.map(f => (
                    <option key={f.key} value={f.key}>
                      {f.label}
                    </option>
                  ))}
                </select>
              </div>
              <div style={{ 
                marginTop: 12, 
                padding: '12px', 
                backgroundColor: '#f8f9fa', 
                border: '1px solid #e0e0e0', 
                borderRadius: '4px' 
              }}>
                <div style={{ fontSize: '0.9rem', fontWeight: 500, marginBottom: 8, color: '#555' }}>
                  Обработка значения
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '8px 12px', alignItems: 'center' }}>
                  <div>
                    <input
                      type="checkbox"
                      checked={stockStrip}
                      onChange={e => setStockStrip(e.target.checked)}
                    />
                  </div>
                  <div style={{ fontSize: '0.9rem', color: '#333' }}>
                    Удалить пробелы в начале и конце строки
                  </div>
                  <div>
                    <input
                      type="checkbox"
                      checked={stockToInt}
                      onChange={e => setStockToInt(e.target.checked)}
                    />
                  </div>
                  <div style={{ fontSize: '0.9rem', color: '#333' }}>
                    Преобразовать в целое число
                  </div>
                </div>
              </div>
            </div>

            {/* Field Block: Barcode */}
            <div style={{ marginBottom: 32 }}>
              <div style={{ marginBottom: 8 }}>
                <div style={{ fontWeight: 600, fontSize: '1rem' }}>
                  Barcode (optional)
                </div>
              </div>
              <div style={{ marginBottom: 12 }}>
                <select
                  style={{ width: '100%', padding: '6px 8px', boxSizing: 'border-box' }}
                  value={barcodeKey}
                  onChange={e => setBarcodeKey(e.target.value)}
                  disabled={sourceFieldsLoading || sourceFields.length === 0}
                >
                  <option value="">
                    {sourceFieldsLoading 
                      ? 'Загрузка полей...' 
                      : sourceFields.length === 0 
                        ? (() => {
                            const { ready } = isSourceReady()
                            if (!ready) {
                              const mode = internalData?.source_mode || internalModeDraft
                              return mode === 'url' ? 'Сначала проверьте источник данных' : 'Сначала загрузите файл'
                            }
                            return 'Источник данных недоступен'
                          })()
                        : '— не выбрано —'}
                  </option>
                  {sourceFields.map(f => (
                    <option key={f.key} value={f.key}>
                      {f.label}
                    </option>
                  ))}
                </select>
              </div>
              <div style={{ 
                marginTop: 12, 
                padding: '12px', 
                backgroundColor: '#f8f9fa', 
                border: '1px solid #e0e0e0', 
                borderRadius: '4px' 
              }}>
                <div style={{ fontSize: '0.9rem', fontWeight: 500, marginBottom: 8, color: '#555' }}>
                  Обработка значения
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '8px 12px', alignItems: 'center' }}>
                  <div>
                    <input
                      type="checkbox"
                      checked={barcodeStrip}
                      onChange={e => setBarcodeStrip(e.target.checked)}
                    />
                  </div>
                  <div style={{ fontSize: '0.9rem', color: '#333' }}>
                    Удалить пробелы в начале и конце строки
                  </div>
                </div>
              </div>
            </div>

            {/* Preview */}
            {mappingPreview && (
              <div style={{ marginTop: 12, marginBottom: 24 }}>
                <h4 style={{ margin: '8px 0' }}>Preview</h4>
                {mappingPreview.rows.length > 0 ? (
                  <table
                    style={{
                      width: '100%',
                      borderCollapse: 'collapse',
                      fontSize: '0.85rem',
                    }}
                  >
                    <thead>
                      <tr>
                        <th style={{ borderBottom: '1px solid #ddd', textAlign: 'left', padding: '4px' }}>internal_sku</th>
                        <th style={{ borderBottom: '1px solid #ddd', textAlign: 'left', padding: '4px' }}>rrp</th>
                        <th style={{ borderBottom: '1px solid #ddd', textAlign: 'left', padding: '4px' }}>stock</th>
                        <th style={{ borderBottom: '1px solid #ddd', textAlign: 'left', padding: '4px' }}>barcode</th>
                      </tr>
                    </thead>
                    <tbody>
                      {mappingPreview.rows.map((row, idx) => (
                        <tr key={idx}>
                          <td style={{ borderBottom: '1px solid #f0f0f0', padding: '4px' }}>{row.internal_sku}</td>
                          <td style={{ borderBottom: '1px solid #f0f0f0', padding: '4px' }}>
                            {row.price && row.price.rrp != null ? row.price.rrp : ''}
                          </td>
                          <td style={{ borderBottom: '1px solid #f0f0f0', padding: '4px' }}>
                            {row.attributes && row.attributes.stock != null ? row.attributes.stock : ''}
                          </td>
                          <td style={{ borderBottom: '1px solid #f0f0f0', padding: '4px' }}>
                            {row.attributes && row.attributes.barcode ? row.attributes.barcode : ''}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <p style={{ fontSize: '0.85rem' }}>Нет валидных строк для предпросмотра.</p>
                )}
                {mappingPreview.errors.length > 0 && (
                  <div style={{ marginTop: 8 }}>
                    <h4 style={{ margin: '4px 0' }}>Errors</h4>
                    <ul style={{ paddingLeft: 16 }}>
                      {mappingPreview.errors.map((e, i) => (
                        <li key={i} style={{ fontSize: '0.8rem', color: 'crimson' }}>
                          {e.row_index >= 0 ? `Row ${e.row_index}: ` : ''}
                          {e.message}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {/* Advanced read-only JSON */}
            <div style={{ marginTop: 32, marginBottom: 24 }}>
              <button
                type="button"
                onClick={() => setShowAdvancedMapping(v => !v)}
                style={{ fontSize: '0.9rem', padding: '6px 12px', cursor: 'pointer' }}
              >
                {showAdvancedMapping ? 'Скрыть технические настройки (JSON)' : 'Показать технические настройки (JSON)'}
              </button>
              <div style={{ fontSize: '0.85rem', color: '#666', marginTop: 6 }}>
                Для продвинутых пользователей. Изменения влияют на обработку данных.
              </div>
              {showAdvancedMapping && (
                <pre
                  style={{
                    marginTop: 12,
                    maxHeight: 200,
                    overflow: 'auto',
                    backgroundColor: '#f5f5f5',
                    padding: 12,
                    fontSize: '0.8rem',
                    border: '1px solid #e0e0e0',
                    borderRadius: '4px',
                  }}
                >
                  {JSON.stringify(buildMappingJson(), null, 2)}
                </pre>
              )}
            </div>

            <div style={{ marginTop: 24, display: 'flex', gap: 8 }}>
              <button onClick={handleValidateMapping} disabled={mappingLoading || !mappingRequiredSelected}>
                {mappingLoading ? 'Проверка...' : 'Validate'}
              </button>
              <button onClick={handleSaveMapping} disabled={mappingLoading || !mappingRequiredSelected}>
                {mappingLoading ? 'Сохранение...' : 'Save'}
              </button>
              <button onClick={() => setShowMappingWizard(false)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
