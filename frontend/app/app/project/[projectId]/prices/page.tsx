'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { apiGetData } from '../../../../../lib/apiClient'

interface PriceRecord {
  nm_id: number
  wb_price: number | null
  wb_discount: number | null
  customer_price: number | null
  rrc: number | null
  snapshot_at: string
}

export default function PricesPage() {
  const params = useParams()
  const router = useRouter()
  const projectId = params.projectId as string
  const [data, setData] = useState<PriceRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [limit] = useState(50)
  const [offset, setOffset] = useState(0)
  const [total, setTotal] = useState(0)

  // Reset state when projectId changes to prevent showing data from previous project
  useEffect(() => {
    setData([])
    setOffset(0)
    setTotal(0)
    setLoading(true)
  }, [projectId])

  useEffect(() => {
    loadData()
  }, [offset, projectId]) // Include projectId in dependencies

  const loadData = async () => {
    try {
      setLoading(true)
      const result = await apiGetData<{ data: PriceRecord[]; total: number }>(`/api/v1/projects/${projectId}/prices/latest?limit=${limit}&offset=${offset}`)
      setData(result.data || [])
      setTotal(result.total || 0)
      setLoading(false)
    } catch (error) {
      console.error('Failed to load prices:', error)
      setLoading(false)
    }
  }

  const formatNumber = (value: number | null): string => {
    if (value === null || value === undefined) return 'N/A'
    return value.toFixed(2)
  }

  return (
    <div className="container">
      <h1>Price Snapshots</h1>
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
                  <th>WB Price</th>
                  <th>WB Discount</th>
                  <th>Customer Price</th>
                  <th>RRC</th>
                  <th>Snapshot At</th>
                </tr>
              </thead>
              <tbody>
                {data.length === 0 ? (
                  <tr>
                    <td colSpan={6} style={{ textAlign: 'center' }}>No data found</td>
                  </tr>
                ) : (
                  data.map((row, idx) => (
                    <tr key={`${row.nm_id}-${idx}`}>
                      <td>{row.nm_id}</td>
                      <td>{formatNumber(row.wb_price)}</td>
                      <td>{formatNumber(row.wb_discount)}</td>
                      <td>{formatNumber(row.customer_price)}</td>
                      <td>{formatNumber(row.rrc)}</td>
                      <td>{new Date(row.snapshot_at).toLocaleString('ru-RU')}</td>
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



