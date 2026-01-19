'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { apiGet } from '../../../../../lib/apiClient'
import '../../../../globals.css'

interface SupplierStockRecord {
  nm_id: number
  barcode: string | null
  supplier_article: string | null
  warehouse_name: string | null
  quantity: number
  quantity_full: number
  last_change_date: string
}

export default function SupplierStocksPage() {
  const params = useParams()
  const router = useRouter()
  const projectId = params.projectId as string
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
      const { data: result } = await apiGet<{ data: SupplierStockRecord[]; total: number }>(
        `/v1/supplier-stocks/latest?limit=${limit}&offset=${offset}`
      )
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
      <Link href={`/app/project/${projectId}/dashboard`}>
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
                  <th>Barcode</th>
                  <th>Supplier Article</th>
                  <th>Warehouse</th>
                  <th>Quantity</th>
                  <th>Quantity Full</th>
                  <th>Last Change</th>
                </tr>
              </thead>
              <tbody>
                {data.length === 0 ? (
                  <tr>
                    <td colSpan={7} style={{ textAlign: 'center' }}>No data found</td>
                  </tr>
                ) : (
                  data.map((row, idx) => (
                    <tr key={`${row.nm_id}-${row.barcode}-${idx}`}>
                      <td>{row.nm_id}</td>
                      <td>{row.barcode || 'N/A'}</td>
                      <td>{row.supplier_article || 'N/A'}</td>
                      <td>{row.warehouse_name || 'N/A'}</td>
                      <td>{row.quantity}</td>
                      <td>{row.quantity_full}</td>
                      <td>{new Date(row.last_change_date).toLocaleString('ru-RU')}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <div className="pagination">
            <button onClick={() => setOffset(Math.max(0, offset - limit))} disabled={offset === 0}>
              Previous
            </button>
            <span>
              Page {Math.floor(offset / limit) + 1} (offset: {offset}, total: {total})
            </span>
            <button onClick={() => setOffset(offset + limit)} disabled={data.length < limit || offset + limit >= total}>
              Next
            </button>
          </div>
        </>
      )}
    </div>
  )
}




