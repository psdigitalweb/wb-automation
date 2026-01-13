'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import './globals.css'

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || '/api'

interface Metrics {
  counts: {
    products: number
    warehouses: number
    stock_snapshots: number
    supplier_stock_snapshots: number
    prices: number
  }
  max_dates: {
    stock_snapshots: string | null
    supplier_stock_snapshots: string | null
    price_snapshots: string | null
  }
}

export default function Dashboard() {
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [loading, setLoading] = useState(true)
  const [toast, setToast] = useState<string | null>(null)

  useEffect(() => {
    loadMetrics()
    // Refresh metrics every 30 seconds
    const interval = setInterval(loadMetrics, 30000)
    return () => clearInterval(interval)
  }, [])

  const loadMetrics = async () => {
    try {
      const res = await fetch(`${API_BASE}/v1/dashboard/metrics`)
      const data = await res.json()
      setMetrics(data)
      setLoading(false)
    } catch (error) {
      console.error('Failed to load metrics:', error)
      setLoading(false)
    }
  }

  const triggerIngest = async (type: string) => {
    try {
      setToast(`Starting ${type} ingestion...`)
      const res = await fetch(`${API_BASE}/v1/ingest/${type}`, {
        method: 'POST'
      })
      const data = await res.json()
      setToast(data.message || `Ingestion ${type} started`)
      setTimeout(() => setToast(null), 3000)
      // Reload metrics after a delay
      setTimeout(loadMetrics, 2000)
    } catch (error) {
      setToast(`Error: ${error}`)
      setTimeout(() => setToast(null), 3000)
    }
  }

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return 'N/A'
    return new Date(dateStr).toLocaleString('ru-RU')
  }

  return (
    <div className="container">
      <h1>WB Automation Dashboard</h1>

      {toast && <div className="toast">{toast}</div>}

      <div className="card">
        <h2>Metrics</h2>
        {loading ? (
          <p>Loading...</p>
        ) : metrics ? (
          <div className="metrics">
            <div className="metric-card">
              <div className="metric-value">{metrics.counts.products}</div>
              <div className="metric-label">Products</div>
            </div>
            <div className="metric-card">
              <div className="metric-value">{metrics.counts.warehouses}</div>
              <div className="metric-label">Warehouses</div>
            </div>
            <div className="metric-card">
              <div className="metric-value">{metrics.counts.stock_snapshots}</div>
              <div className="metric-label">Stock Snapshots</div>
            </div>
            <div className="metric-card">
              <div className="metric-value">{metrics.counts.supplier_stock_snapshots}</div>
              <div className="metric-label">Supplier Stock Snapshots</div>
            </div>
            <div className="metric-card">
              <div className="metric-value">{metrics.counts.prices}</div>
              <div className="metric-label">Latest Prices</div>
            </div>
          </div>
        ) : (
          <p>Failed to load metrics</p>
        )}

        {metrics && (
          <div style={{ marginTop: '20px' }}>
            <p><strong>Last Stock Snapshot:</strong> {formatDate(metrics.max_dates.stock_snapshots)}</p>
            <p><strong>Last Supplier Stock:</strong> {formatDate(metrics.max_dates.supplier_stock_snapshots)}</p>
            <p><strong>Last Price Snapshot:</strong> {formatDate(metrics.max_dates.price_snapshots)}</p>
          </div>
        )}
      </div>

      <div className="card">
        <h2>Ingestion Controls</h2>
        <button onClick={() => triggerIngest('warehouses')}>
          Run Warehouses Ingestion
        </button>
        <button onClick={() => triggerIngest('stocks')}>
          Run Stocks Ingestion
        </button>
        <button onClick={() => triggerIngest('supplier-stocks')}>
          Run Supplier Stocks Ingestion
        </button>
        <button onClick={() => triggerIngest('prices')}>
          Run Prices Ingestion
        </button>
      </div>

      <div className="card">
        <h2>Navigation</h2>
        <Link href="/stocks">
          <button>View Stocks</button>
        </Link>
        <Link href="/supplier-stocks">
          <button>View Supplier Stocks</button>
        </Link>
        <Link href="/prices">
          <button>View Prices</button>
        </Link>
      </div>
    </div>
  )
}

