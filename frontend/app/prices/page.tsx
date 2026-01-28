'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { getApiBase } from '@/lib/api'

const API_BASE = getApiBase()

interface PriceRecord {
  nm_id: number
  wb_price: number | null
  wb_discount: number | null
  spp: number | null
  customer_price: number | null
  rrc: number | null
  snapshot_at: string
}

export default function PricesPage() {
  const [data, setData] = useState<PriceRecord[]>([])
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
      const res = await fetch(`${API_BASE}/api/v1/prices/latest?limit=${limit}&offset=${offset}`)
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`)
      }
      const result = await res.json()
      setData(result.data || [])
      setTotal(result.total || 0)
      setLoading(false)
    } catch (error) {
      console.error('Failed to load prices:', error)
      setLoading(false)
    }
  }

  return (
    <div className="container">
      <h1>Price Snapshots</h1>
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
                  <th>WB Price</th>
                  <th>WB Discount</th>
                  <th>SPP</th>
                  <th>Customer Price</th>
                  <th>RRC</th>
                  <th>Snapshot At</th>
                </tr>
              </thead>
              <tbody>
                {data.map((row, idx) => (
                  <tr key={`${row.nm_id}-${idx}`}>
                    <td>{row.nm_id}</td>
                    <td>{row.wb_price?.toFixed(2) ?? 'N/A'}</td>
                    <td>{row.wb_discount?.toFixed(2) ?? 'N/A'}</td>
                    <td>{row.spp?.toFixed(2) ?? 'N/A'}</td>
                    <td>{row.customer_price?.toFixed(2) ?? 'N/A'}</td>
                    <td>{row.rrc?.toFixed(2) ?? 'N/A'}</td>
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

