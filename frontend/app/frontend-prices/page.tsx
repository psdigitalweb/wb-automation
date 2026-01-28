'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { getApiBase } from '@/lib/api'

const API_BASE = getApiBase()
const PAGE_SIZE = 50

interface FrontendPrice {
  id: number
  snapshot_at: string
  source: string
  query_type: string
  query_value: string
  page: number
  nm_id: number
  vendor_code: string | null
  name: string | null
  price_basic: number | null
  price_product: number | null
  sale_percent: number | null
  discount_calc_percent: number | null
}

interface FrontendPricesResponse {
  data: FrontendPrice[]
  limit: number
  offset: number
  count: number
  total: number
}

export default function FrontendPricesPage() {
  const [prices, setPrices] = useState<FrontendPrice[]>([])
  const [loading, setLoading] = useState(true)
  const [offset, setOffset] = useState(0)
  const [total, setTotal] = useState(0)
  const [toast, setToast] = useState<string | null>(null)
  
  // Form state
  const [brandId, setBrandId] = useState('41189')
  const [baseUrl, setBaseUrl] = useState('')
  const [maxPages, setMaxPages] = useState('2')
  const [sleepMs, setSleepMs] = useState('800')
  const [ingesting, setIngesting] = useState(false)
  const [savingUrl, setSavingUrl] = useState(false)
  const [urlLoaded, setUrlLoaded] = useState(false)

  useEffect(() => {
    loadPrices()
    loadBrandUrl()
  }, [offset])

  const loadBrandUrl = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/settings/frontend-prices/brand-url`)
      if (res.ok) {
        const data = await res.json()
        setBaseUrl(data.url || '')
        setUrlLoaded(true)
      }
    } catch (error) {
      console.error('Failed to load brand URL:', error)
    }
  }

  const handleSaveUrl = async () => {
    if (!baseUrl.trim()) {
      setToast('URL cannot be empty')
      setTimeout(() => setToast(null), 3000)
      return
    }
    
    setSavingUrl(true)
    try {
      const res = await fetch(`${API_BASE}/api/v1/settings/frontend-prices/brand-url`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: baseUrl.trim() })
      })
      if (res.ok) {
        setToast('URL saved successfully')
        setTimeout(() => setToast(null), 3000)
      } else {
        const data = await res.json()
        setToast(`Error: ${data.detail || 'Failed to save URL'}`)
        setTimeout(() => setToast(null), 3000)
      }
    } catch (error) {
      setToast(`Error: ${error}`)
      setTimeout(() => setToast(null), 3000)
    } finally {
      setSavingUrl(false)
    }
  }

  const loadPrices = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/api/v1/frontend-prices/latest?limit=${PAGE_SIZE}&offset=${offset}`)
      const data: FrontendPricesResponse = await res.json()
      setPrices(data.data)
      setTotal(data.total)
      setLoading(false)
    } catch (error) {
      console.error('Failed to load frontend prices:', error)
      setLoading(false)
    }
  }

  const handleNextPage = () => {
    if (offset + PAGE_SIZE < total) {
      setOffset(prev => prev + PAGE_SIZE)
    }
  }

  const handlePrevPage = () => {
    if (offset > 0) {
      setOffset(prev => prev - PAGE_SIZE)
    }
  }

  const handleIngest = async () => {
    setIngesting(true)
    try {
      const requestBody: any = {
        brand_id: parseInt(brandId) || 41189,
        max_pages: parseInt(maxPages) || 0,
        sleep_ms: parseInt(sleepMs) || 800
      }
      
      // Only include base_url if it's provided (otherwise server will use default from settings)
      if (baseUrl.trim()) {
        requestBody.base_url = baseUrl.trim()
      }
      
      const res = await fetch(`${API_BASE}/api/v1/ingest/frontend-prices/brand`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody)
      })
      const data = await res.json()
      
      if (data.error) {
        setToast(`Error: ${data.error}`)
        setTimeout(() => setToast(null), 5000)
      } else {
        setToast(data.message || `Ingestion ${data.status}`)
        setTimeout(() => setToast(null), 5000)
        
        // Reload prices after a delay
        setTimeout(loadPrices, 2000)
      }
    } catch (error) {
      setToast(`Error: ${error}`)
      setTimeout(() => setToast(null), 3000)
    } finally {
      setIngesting(false)
    }
  }

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString('ru-RU')
  }

  return (
    <div className="container">
      <h1>Frontend Catalog Prices</h1>
      <Link href="/">
        <button className="back-button">Back to Dashboard</button>
      </Link>

      {toast && <div className="toast">{toast}</div>}

      <div className="card" style={{ marginTop: '20px' }}>
        <h2>Run Ingestion</h2>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', maxWidth: '600px' }}>
          <div>
            <label>Brand ID:</label>
            <input 
              type="text" 
              value={brandId} 
              onChange={(e) => setBrandId(e.target.value)}
              placeholder="41189"
            />
          </div>
          <div>
            <label>Base URL (with page=1):</label>
            <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
              <input 
                type="text" 
                value={baseUrl} 
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="https://catalog.wb.ru/brands/v4/catalog?...&page=1..."
                style={{ flex: 1 }}
                disabled={!urlLoaded}
              />
              <button onClick={handleSaveUrl} disabled={savingUrl || !urlLoaded}>
                {savingUrl ? 'Saving...' : 'Save URL'}
              </button>
            </div>
            {!urlLoaded && <small style={{ color: '#666' }}>Loading URL from settings...</small>}
            <small style={{ color: '#666', display: 'block', marginTop: '5px' }}>
              Leave empty to use saved URL from settings
            </small>
          </div>
          <div>
            <label>Max Pages (0 = until empty):</label>
            <input 
              type="number" 
              value={maxPages} 
              onChange={(e) => setMaxPages(e.target.value)}
              placeholder="2"
            />
          </div>
          <div>
            <label>Sleep between pages (ms):</label>
            <input 
              type="number" 
              value={sleepMs} 
              onChange={(e) => setSleepMs(e.target.value)}
              placeholder="800"
            />
          </div>
          <button onClick={handleIngest} disabled={ingesting}>
            {ingesting ? 'Running...' : 'Run Frontend Brand Prices Ingestion'}
          </button>
        </div>
      </div>

      {loading ? (
        <p>Loading prices...</p>
      ) : prices.length > 0 ? (
        <>
          <p>Total prices: {total}</p>
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Snapshot At</th>
                  <th>Brand ID</th>
                  <th>Page</th>
                  <th>NM ID</th>
                  <th>Name</th>
                  <th>Price Basic</th>
                  <th>Price Product</th>
                  <th>Sale %</th>
                  <th>Discount %</th>
                </tr>
              </thead>
              <tbody>
                {prices.map(price => (
                  <tr key={price.id}>
                    <td>{formatDate(price.snapshot_at)}</td>
                    <td>{price.query_value}</td>
                    <td>{price.page}</td>
                    <td>{price.nm_id}</td>
                    <td>{price.name || 'N/A'}</td>
                    <td>{price.price_basic?.toFixed(2) || 'N/A'}</td>
                    <td>{price.price_product?.toFixed(2) || 'N/A'}</td>
                    <td>{price.sale_percent || 'N/A'}</td>
                    <td>{price.discount_calc_percent || 'N/A'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pagination">
            <button onClick={handlePrevPage} disabled={offset === 0}>Previous</button>
            <span>Page {offset / PAGE_SIZE + 1} of {Math.ceil(total / PAGE_SIZE)}</span>
            <button onClick={handleNextPage} disabled={offset + PAGE_SIZE >= total}>Next</button>
          </div>
        </>
      ) : (
        <p>No frontend price data available. Run ingestion from the form above.</p>
      )}
    </div>
  )
}

