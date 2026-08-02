'use client'

import { FormEvent, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { apiGetData, apiPutData, getApiErrorMessage } from '../../../../../../lib/apiClient'
import { usePageTitle } from '../../../../../../hooks/usePageTitle'
import styles from './taxes.module.css'

const WB_UNIT_PNL_PROFILE_CODE = 'wb_transfer_minus_vat_wb_cogs_tax'

interface TaxProfile {
  project_id: number
  model_code: string
  params_json: Record<string, unknown>
  updated_at: string
}

interface TaxProfileModel {
  model_code: string
  title: string
  short_title: string
  description: string
  formula: string
  base_kind: string
  tax_rate_label: string
  default_tax_percent: number
  default_vat_percent: number
  vat_options: number[]
  supported_views: string[]
}

function decimalParam(params: Record<string, unknown>, key: string): number | null {
  const value = Number(params[key])
  return Number.isFinite(value) ? value : null
}

function fractionToInclusivePercent(fraction: number): number {
  if (fraction <= 0) return 0
  if (fraction >= 1) return 100
  return Math.round(((fraction / (1 - fraction)) * 100) * 1_000_000) / 1_000_000
}

function visiblePercent(value: string): string {
  const parsed = Number(value.replace(',', '.'))
  if (!Number.isFinite(parsed)) return '—'
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(parsed)
}

export default function TaxesSettingsPage() {
  const params = useParams()
  const projectId = params.projectId as string
  usePageTitle('Налоги', projectId)

  const [profile, setProfile] = useState<TaxProfile | null>(null)
  const [models, setModels] = useState<TaxProfileModel[]>([])
  const [selectedModelCode, setSelectedModelCode] = useState(WB_UNIT_PNL_PROFILE_CODE)
  const [vatPercent, setVatPercent] = useState('5')
  const [taxPercent, setTaxPercent] = useState('15')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const activeModel = useMemo(
    () => models.find((model) => model.model_code === selectedModelCode),
    [models, selectedModelCode],
  )

  useEffect(() => {
    let alive = true

    async function load() {
      try {
        setLoading(true)
        setError(null)
        const availableModels = await apiGetData<TaxProfileModel[]>(
          `/api/v1/projects/${projectId}/taxes/profile-models`,
        )
        if (alive) {
          setModels(availableModels)
          if (availableModels[0]) {
            setSelectedModelCode(availableModels[0].model_code)
            setTaxPercent(String(availableModels[0].default_tax_percent))
            setVatPercent(String(availableModels[0].default_vat_percent))
          }
        }

        try {
          const currentProfile = await apiGetData<TaxProfile>(
            `/api/v1/projects/${projectId}/taxes/profile`,
          )
          if (!alive) return
          setProfile(currentProfile)

          const configuredModel = availableModels.find(
            (model) => model.model_code === currentProfile.model_code,
          )
          if (configuredModel) {
            setSelectedModelCode(currentProfile.model_code)
            const vatRate = decimalParam(currentProfile.params_json, 'vat_rate')
            const taxRate = decimalParam(currentProfile.params_json, 'tax_rate')
            if (vatRate != null) setVatPercent(String(fractionToInclusivePercent(vatRate)))
            if (taxRate != null) setTaxPercent(String(taxRate * 100))
          }
        } catch (profileError: unknown) {
          const status = (profileError as { status?: number })?.status
          if (status !== 404) throw profileError
          if (alive) setProfile(null)
        }
      } catch (loadError: unknown) {
        if (alive) setError(getApiErrorMessage(loadError, 'Не удалось загрузить настройки налогов'))
      } finally {
        if (alive) setLoading(false)
      }
    }

    load()
    return () => {
      alive = false
    }
  }, [projectId])

  function selectModel(modelCode: string) {
    const model = models.find((item) => item.model_code === modelCode)
    if (!model) return
    setSelectedModelCode(modelCode)
    setTaxPercent(String(model.default_tax_percent))
    setVatPercent(String(model.default_vat_percent))
    setError(null)
    setSuccess(null)
  }

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setSuccess(null)

    const vat = Number(vatPercent.replace(',', '.'))
    const tax = Number(taxPercent.replace(',', '.'))
    if (!Number.isFinite(vat) || vat < 0 || vat > 100) {
      setError('Ставка НДС должна быть от 0 до 100%.')
      return
    }
    if (!Number.isFinite(tax) || tax < 0 || tax > 100) {
      setError('Ставка налога должна быть от 0 до 100%.')
      return
    }

    const vatRate = vat === 0 ? 0 : vat / (100 + vat)

    try {
      setSaving(true)
      const saved = await apiPutData<TaxProfile>(
        `/api/v1/projects/${projectId}/taxes/profile`,
        {
          model_code: selectedModelCode,
          params_json: {
            vat_rate: String(vatRate),
            tax_rate: String(tax / 100),
          },
        },
      )
      setProfile(saved)
      setSuccess('Профиль подключён. Новые ставки применяются к Unit P&L сразу.')
    } catch (saveError: unknown) {
      setError(getApiErrorMessage(saveError, 'Не удалось сохранить налоговый профиль'))
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div className={styles.loading}>Загрузка налогового профиля…</div>
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <div className={styles.eyebrow}>Настройки проекта</div>
          <h1>Налоговый режим</h1>
          <p>Ставки и правила расчёта налогов для финансового отчёта Wildberries.</p>
        </div>
        <Link className={styles.backLink} href={`/app/project/${projectId}/settings`}>
          ← К настройкам
        </Link>
      </header>

      {error && <div className={styles.errorBanner}>{error}</div>}
      {success && <div className={styles.successBanner}>{success}</div>}

      {profile && !models.some((model) => model.model_code === profile.model_code) && (
        <div className={styles.warningBanner}>
          Сохранён устаревший профиль <code>{profile.model_code}</code>. Unit P&amp;L его не применяет.
          Сохраните профиль ниже, чтобы включить расчёт.
        </div>
      )}

      <section className={styles.profileCard}>
        <div className={styles.cardHeader}>
          <div>
            <div className={styles.profileMeta}>
              <span className={styles.badge}>Wildberries</span>
              <span>Управленческая оценка</span>
            </div>
            <h2>{activeModel?.title ?? 'Налоговый профиль'}</h2>
          </div>
          <span className={profile?.model_code === selectedModelCode ? styles.active : styles.inactive}>
            {profile?.model_code === selectedModelCode ? 'Подключён' : 'Не подключён'}
          </span>
        </div>

        <label className={styles.profileSelector}>
          <span>Профиль расчёта</span>
          <select value={selectedModelCode} onChange={(event) => selectModel(event.target.value)}>
            {models.map((model) => (
              <option key={model.model_code} value={model.model_code}>
                {model.title}
              </option>
            ))}
          </select>
        </label>

        <p className={styles.description}>
          {activeModel?.description ?? 'Налог рассчитывается только с положительной базы за выбранный период.'}
        </p>

        <div className={styles.rateGrid}>
          <div className={styles.rateCard}>
            <span>НДС</span>
            <strong>{visiblePercent(vatPercent)}%</strong>
            <small>{Number(vatPercent) > 0 ? 'Выделяется из выручки' : 'Освобождение / не применяется'}</small>
          </div>
          <div className={styles.rateCard}>
            <span>{activeModel?.short_title ?? 'Налог'}</span>
            <strong>{visiblePercent(taxPercent)}%</strong>
            <small>{activeModel?.tax_rate_label ?? 'Основная ставка профиля'}</small>
          </div>
          <div className={styles.applicationCard}>
            <span>Применяется</span>
            <strong>К итогам периода</strong>
            <small>В Unit P&amp;L, без распределения налога по SKU</small>
          </div>
        </div>

        <div className={styles.calculationBlock}>
          <div className={styles.calculationTitle}>Как считается</div>
          <div className={styles.formulaText}>{activeModel?.formula}</div>
          <p>Расчёт выполняется по данным выбранного периода и не заменяет налоговый учёт.</p>
        </div>

        <form className={styles.form} onSubmit={saveProfile}>
          <div className={styles.formHeader}>
            <h3>Ставки режима</h3>
            <span>Изменения сразу применятся в Unit P&amp;L</span>
          </div>
          <div className={styles.fields}>
            <label>
              <span>Режим НДС</span>
              <select
                value={vatPercent}
                onChange={(event) => setVatPercent(event.target.value)}
                disabled={(activeModel?.vat_options.length ?? 0) <= 1}
              >
                {(activeModel?.vat_options ?? [0]).map((rate) => (
                  <option key={rate} value={String(rate)}>
                    {rate === 0 ? 'Без НДС' : `НДС ${rate}% (включён в цену)`}
                  </option>
                ))}
              </select>
              <small>Для включённого НДС применяется расчётная доля ставки, например 5/105.</small>
            </label>

            <label>
              <span>{activeModel?.tax_rate_label ?? 'Ставка налога'}</span>
              <input
                type="number"
                min="0"
                max="100"
                step="0.01"
                value={taxPercent}
                onChange={(event) => setTaxPercent(event.target.value)}
                required
              />
              <small>Можно изменить для региональной или индивидуальной управленческой модели.</small>
            </label>
          </div>

          <div className={styles.scopeNote}>
            <strong>Управленческая оценка:</strong> профиль показывает влияние налоговой нагрузки на прибыль
            по данным EcomCore и не является расчётом обязательств перед ФНС.
          </div>

          <div className={styles.actions}>
            <button className={styles.primaryButton} type="submit" disabled={saving}>
              {saving
                ? 'Сохранение…'
                : profile?.model_code === selectedModelCode
                  ? 'Сохранить ставки'
                  : 'Подключить профиль'}
            </button>
            {profile?.model_code === selectedModelCode && (
              <span className={styles.updatedAt}>
                Обновлён {new Date(profile.updated_at).toLocaleString('ru-RU')}
              </span>
            )}
          </div>
        </form>
      </section>
      <Link className={styles.reportLink} href={`/app/project/${projectId}/wildberries/finances/unit-pnl`}>
        Открыть Unit P&amp;L и посмотреть расчёт →
      </Link>
    </div>
  )
}
