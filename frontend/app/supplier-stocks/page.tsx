'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import '../globals.css'

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || '/api'

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

  useEffect(() => {
    loadData()
  }, [offset])

  const loadData = async () => {
    try {
      setLoading(true)
      const res = await fetch(`${API_BASE}/v1/supplier-stocks/latest?limit=${limit}&offset=${offset}`)
      const result = await res.json()
      setData(result.data || [])
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
            <span>Page {Math.floor(offset / limit) + 1} (offset: {offset})</span>
            <button onClick={() => setOffset(offset + limit)} disabled={data.length < limit}>
              Next
            </button>
          </div>
        </>
      )}
    </div>
  )
}

