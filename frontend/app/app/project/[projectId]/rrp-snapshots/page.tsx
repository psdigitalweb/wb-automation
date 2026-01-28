'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { apiGetData } from '../../../../../lib/apiClient'

interface RrpRecord {
  snapshot_at: string
  vendor_code_raw: string | null
  vendor_code_norm: string | null
  barcode: string | null
  rrp_price: number | null
  rrp_stock: number | null
}

interface RrpResponse {
  data: RrpRecord[]
  limit: number
  offset: number
  count: number
  total: number
}

export default function RrpSnapshotsPage() {
  const params = useParams()
  const router = useRouter()
  const projectId = params.projectId as string
  const [data, setData] = useState<RrpRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [limit] = useState(50)
  const [offset, setOffset] = useState(0)
  const [total, setTotal] = useState(0)

  // Reset state when projectId changes
  useEffect(() => {
    setData([])
    setOffset(0)
    setTotal(0)
    setLoading(true)
  }, [projectId])

  useEffect(() => {
    loadData()
  }, [offset, projectId])

  const loadData = async () => {
    try {
      setLoading(true)
      const result = await apiGetData<RrpResponse>(`/api/v1/projects/${projectId}/rrp/latest?limit=${limit}&offset=${offset}`)
      setData(result.data || [])
      setTotal(result.total || 0)
      setLoading(false)
    } catch (error) {
      console.error('Failed to load RRP snapshots:', error)
      setLoading(false)
    }
  }

  const formatNumber = (value: number | null): string => {
    if (value === null || value === undefined) return 'N/A'
    return value.toFixed(2)
  }

  const formatInt = (value: number | null): string => {
    if (value === null || value === undefined) return 'N/A'
    return value.toString()
  }

  const formatDate = (dateStr: string | null): string => {
    if (!dateStr) return 'N/A'
    try {
      return new Date(dateStr).toLocaleString('ru-RU')
    } catch {
      return 'N/A'
    }
  }

  return (
    <div className="container">
      <h1>RRP Snapshots (1C XML)</h1>
      <Link href={`/app/project/${projectId}/dashboard`}>
        <button>← Back to Dashboard</button>
      </Link>

      {loading ? (
        <p>Loading...</p>
      ) : (
        <>
          <div className="card">
            <div style={{ marginBottom: '10px' }}>
              <strong>Total: {total}</strong> | Showing {data.length} records
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table>
                <thead>
                  <tr>
                    <th>Snapshot At</th>
                    <th>Vendor Code (Raw)</th>
                    <th>Vendor Code (Norm)</th>
                    <th>Barcode</th>
                    <th>RRP Price</th>
                    <th>RRP Stock</th>
                  </tr>
                </thead>
                <tbody>
                  {data.length === 0 ? (
                    <tr>
                      <td colSpan={6} style={{ textAlign: 'center' }}>No data found</td>
                    </tr>
                  ) : (
                    data.map((row, idx) => (
                      <tr key={`${row.vendor_code_norm}-${row.barcode}-${row.snapshot_at}-${idx}`}>
                        <td>{formatDate(row.snapshot_at)}</td>
                        <td>{row.vendor_code_raw || 'N/A'}</td>
                        <td>{row.vendor_code_norm || 'N/A'}</td>
                        <td>{row.barcode || 'N/A'}</td>
                        <td>{formatNumber(row.rrp_price)}</td>
                        <td>{formatInt(row.rrp_stock)}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="pagination">
            <button onClick={() => setOffset(Math.max(0, offset - limit))} disabled={offset === 0}>
              Previous
            </button>
            <span>
              Page {Math.floor(offset / limit) + 1} of {Math.ceil(total / limit)} (Total: {total}, Showing: {data.length})
            </span>
            <button onClick={() => setOffset(offset + limit)} disabled={offset + limit >= total}>
              Next
            </button>
          </div>
        </>
      )}
    </div>
  )
}




