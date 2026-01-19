'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import '../globals.css'
import { getApiBase } from '@/lib/api'

const API_BASE = getApiBase()

interface StockRecord {
  nm_id: number
  warehouse_wb_id: number | null
  quantity: number
  snapshot_at: string
}

export default function StocksPage() {
  const [data, setData] = useState<StockRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [limit] = useState(50)
  const [offset, setOffset] = useState(0)
  const [total, setTotal] = useState(0)

  useEffect(() => {
    loadData()
  }, [offset])

  const loadData = async () => {
    try {
      setLoading(true)
      const res = await fetch(`${API_BASE}/v1/stocks/latest?limit=${limit}&offset=${offset}`)
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`)
      }
      const result = await res.json()
      setData(result.data || [])
      setTotal(result.total || 0)
      setLoading(false)
    } catch (error) {
      console.error('Failed to load stocks:', error)
      setLoading(false)
    }
  }

  return (
    <div className="container">
      <h1>Stock Snapshots</h1>
      <Link href="/">
        <button>← Back to Dashboard</button>
      </Link>

      {loading ? (
        <p>Loading...</p>
      ) : (
        <>
          <div className="card">
            <table>
              <thead>
                <tr>
                  <th>NM ID</th>
                  <th>Warehouse ID</th>
                  <th>Quantity</th>
                  <th>Snapshot At</th>
                </tr>
              </thead>
              <tbody>
                {data.map((row, idx) => (
                  <tr key={`${row.nm_id}-${row.warehouse_wb_id}-${idx}`}>
                    <td>{row.nm_id}</td>
                    <td>{row.warehouse_wb_id || 'N/A'}</td>
                    <td>{row.quantity}</td>
                    <td>{new Date(row.snapshot_at).toLocaleString('ru-RU')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="pagination">
            <button onClick={() => setOffset(Math.max(0, offset - limit))} disabled={offset === 0}>
              Previous
            </button>
            <span>Page {Math.floor(offset / limit) + 1} of {Math.ceil(total / limit)} (Total: {total}, Showing: {data.length})</span>
            <button onClick={() => setOffset(offset + limit)} disabled={offset + limit >= total}>
              Next
            </button>
          </div>
        </>
      )}
    </div>
  )
}

