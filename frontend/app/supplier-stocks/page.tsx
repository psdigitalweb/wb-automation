'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import '../globals.css'
import { getApiBase } from '@/lib/api'

const API_BASE = getApiBase()

interface SupplierStockRecord {
  snapshot_at: string
  last_change_date: string
  warehouse_name: string | null
  nm_id: number
  supplier_article: string | null
  barcode: string | null
  tech_size: string | null
  quantity: number
  quantity_full: number | null
  in_way_to_client: number | null
  in_way_from_client: number | null
  is_supply: boolean | null
  is_realization: boolean | null
  price: number | null
  discount: number | null
}

export default function SupplierStocksPage() {
  const [data, setData] = useState<SupplierStockRecord[]>([])
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
      const res = await fetch(`${API_BASE}/v1/supplier-stocks/latest?limit=${limit}&offset=${offset}`)
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`)
      }
      const result = await res.json()
      setData(result.data || [])
      setTotal(result.total || 0)
      setLoading(false)
    } catch (error) {
      console.error('Failed to load supplier stocks:', error)
      setLoading(false)
    }
  }

  return (
    <div className="container">
      <h1>Supplier Stock Snapshots</h1>
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
                  <th>Warehouse</th>
                  <th>Barcode</th>
                  <th>Quantity</th>
                  <th>Quantity Full</th>
                  <th>In Way To Client</th>
                  <th>In Way From Client</th>
                  <th>Last Change Date</th>
                </tr>
              </thead>
              <tbody>
                {data.map((row, idx) => (
                  <tr key={`${row.nm_id}-${row.barcode}-${idx}`}>
                    <td>{row.nm_id}</td>
                    <td>{row.warehouse_name || 'N/A'}</td>
                    <td>{row.barcode || 'N/A'}</td>
                    <td>{row.quantity}</td>
                    <td>{row.quantity_full ?? 'N/A'}</td>
                    <td>{row.in_way_to_client ?? 'N/A'}</td>
                    <td>{row.in_way_from_client ?? 'N/A'}</td>
                    <td>{new Date(row.last_change_date).toLocaleString('ru-RU')}</td>
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

