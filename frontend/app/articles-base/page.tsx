'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import '../globals.css'
import { getApiBase } from '@/lib/api'

interface ArticleRecord {
  'Артикул': string | null
  'NMid': number | null
  'ШК': string | null
  'Наша цена (РРЦ)': number | null
  'Цена на витрине': number | null
  'Скидка наша': number | null
  'СПП': number | null
  'Остаток WB': number | null
  'Остаток 1С': number | null
  'Обновлено WB': string | null
  'Обновлено 1С': string | null
  'Обновлено фронт': string | null
  'Обновлено WB API': string | null
}

interface ArticleBaseResponse {
  data: ArticleRecord[]
  limit: number
  offset: number
  count: number
  total: number
}

type SortColumn = 'Артикул' | 'NMid' | 'ШК' | 'Наша цена (РРЦ)' | 'Цена на витрине' | 'Скидка наша' | 'СПП' | 'Остаток WB' | 'Остаток 1С' | 'Обновлено WB' | 'Обновлено 1С'
type SortOrder = 'asc' | 'desc'

export default function ArticlesBasePage() {
  const [data, setData] = useState<ArticleRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [limit] = useState(50)
  const [offset, setOffset] = useState(0)
  const [total, setTotal] = useState(0)
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [sortBy, setSortBy] = useState<SortColumn>('NMid')
  const [sortOrder, setSortOrder] = useState<SortOrder>('asc')
  const [onlyWithWbStock, setOnlyWithWbStock] = useState(false)
  const [onlyWithOurStock, setOnlyWithOurStock] = useState(false)

  useEffect(() => {
    loadData()
  }, [offset, search, sortBy, sortOrder, onlyWithWbStock, onlyWithOurStock])

  const loadData = async () => {
    try {
      setLoading(true)
      const apiBase = getApiBase()
      const params = new URLSearchParams({
        limit: limit.toString(),
        offset: offset.toString(),
        sort_by: sortBy,
        sort_order: sortOrder,
      })
      if (search) {
        params.append('search', search)
      }
      if (onlyWithWbStock) {
        params.append('only_with_wb_stock', 'true')
      }
      if (onlyWithOurStock) {
        params.append('only_with_our_stock', 'true')
      }
      const url = `${apiBase}/v1/articles/base?${params}`
      console.log('Fetching from:', url)
      const res = await fetch(url)
      console.log('Response status:', res.status, res.statusText)
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`)
      }
      const result: ArticleBaseResponse = await res.json()
      console.log('API response:', { total: result.total, count: result.count, dataLength: result.data?.length })
      setData(result.data || [])
      setTotal(result.total || 0)
      setLoading(false)
    } catch (error) {
      console.error('Failed to load articles:', error)
      setLoading(false)
    }
  }

  const handleSearch = () => {
    setSearch(searchInput)
    setOffset(0) // Reset to first page
  }

  const handleKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleSearch()
    }
  }

  const handleSort = (column: SortColumn) => {
    if (sortBy === column) {
      // Toggle sort order
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
    } else {
      // New column, default to asc
      setSortBy(column)
      setSortOrder('asc')
    }
    setOffset(0) // Reset to first page
  }

  const getSortIcon = (column: SortColumn) => {
    if (sortBy !== column) {
      return '↕️'
    }
    return sortOrder === 'asc' ? '↑' : '↓'
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
      <h1>Article Base Showcase</h1>
      <Link href="/">
        <button>← Back to Dashboard</button>
      </Link>

      <div className="card" style={{ marginTop: '20px', marginBottom: '20px' }}>
        <h2>Search & Filters</h2>
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center', marginBottom: '10px' }}>
          <input
            type="text"
            placeholder="Search by артикул or NMid..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyPress={handleKeyPress}
            style={{ flex: 1, padding: '8px', fontSize: '14px' }}
          />
          <button onClick={handleSearch}>Search</button>
          {search && (
            <button onClick={() => { setSearch(''); setSearchInput(''); setOffset(0); }}>
              Clear
            </button>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '5px', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={onlyWithWbStock}
              onChange={(e) => {
                setOnlyWithWbStock(e.target.checked)
                setOffset(0)
              }}
            />
            <span>Только с наличием на ВБ</span>
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '5px', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={onlyWithOurStock}
              onChange={(e) => {
                setOnlyWithOurStock(e.target.checked)
                setOffset(0)
              }}
            />
            <span>Только с наличием на нашем складе</span>
          </label>
        </div>
        {search && (
          <p style={{ marginTop: '10px', color: '#666' }}>
            Searching for: <strong>{search}</strong>
          </p>
        )}
      </div>

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
                    <th 
                      onClick={() => handleSort('Артикул')}
                      style={{ cursor: 'pointer', userSelect: 'none' }}
                      title="Click to sort"
                    >
                      Артикул {getSortIcon('Артикул')}
                    </th>
                    <th 
                      onClick={() => handleSort('NMid')}
                      style={{ cursor: 'pointer', userSelect: 'none' }}
                      title="Click to sort"
                    >
                      NMid {getSortIcon('NMid')}
                    </th>
                    <th 
                      onClick={() => handleSort('ШК')}
                      style={{ cursor: 'pointer', userSelect: 'none' }}
                      title="Click to sort"
                    >
                      ШК {getSortIcon('ШК')}
                    </th>
                    <th 
                      onClick={() => handleSort('Наша цена (РРЦ)')}
                      style={{ cursor: 'pointer', userSelect: 'none' }}
                      title="Click to sort"
                    >
                      Наша цена (РРЦ) {getSortIcon('Наша цена (РРЦ)')}
                    </th>
                    <th 
                      onClick={() => handleSort('Цена на витрине')}
                      style={{ cursor: 'pointer', userSelect: 'none' }}
                      title="Click to sort"
                    >
                      Цена на витрине {getSortIcon('Цена на витрине')}
                    </th>
                    <th 
                      onClick={() => handleSort('Скидка наша')}
                      style={{ cursor: 'pointer', userSelect: 'none' }}
                      title="Click to sort"
                    >
                      Скидка наша {getSortIcon('Скидка наша')}
                    </th>
                    <th 
                      onClick={() => handleSort('СПП')}
                      style={{ cursor: 'pointer', userSelect: 'none' }}
                      title="Click to sort"
                    >
                      СПП {getSortIcon('СПП')}
                    </th>
                    <th 
                      onClick={() => handleSort('Остаток WB')}
                      style={{ cursor: 'pointer', userSelect: 'none' }}
                      title="Click to sort"
                    >
                      Остаток WB {getSortIcon('Остаток WB')}
                    </th>
                    <th 
                      onClick={() => handleSort('Остаток 1С')}
                      style={{ cursor: 'pointer', userSelect: 'none' }}
                      title="Click to sort"
                    >
                      Остаток 1С {getSortIcon('Остаток 1С')}
                    </th>
                    <th 
                      onClick={() => handleSort('Обновлено WB')}
                      style={{ cursor: 'pointer', userSelect: 'none' }}
                      title="Click to sort"
                    >
                      Обновлено WB {getSortIcon('Обновлено WB')}
                    </th>
                    <th 
                      onClick={() => handleSort('Обновлено 1С')}
                      style={{ cursor: 'pointer', userSelect: 'none' }}
                      title="Click to sort"
                    >
                      Обновлено 1С {getSortIcon('Обновлено 1С')}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.length === 0 ? (
                    <tr>
                      <td colSpan={11} style={{ textAlign: 'center' }}>
                        No data found
                      </td>
                    </tr>
                  ) : (
                    data.map((row, idx) => (
                      <tr key={`${row['NMid']}-${row['Артикул']}-${idx}`}>
                        <td>{row['Артикул'] || 'N/A'}</td>
                        <td>{row['NMid'] || 'N/A'}</td>
                        <td>{row['ШК'] || 'N/A'}</td>
                        <td>{formatNumber(row['Наша цена (РРЦ)'])}</td>
                        <td>{formatNumber(row['Цена на витрине'])}</td>
                        <td>{formatNumber(row['Скидка наша'])}</td>
                        <td>{formatInt(row['СПП'])}</td>
                        <td>{formatInt(row['Остаток WB'])}</td>
                        <td>{formatInt(row['Остаток 1С'])}</td>
                        <td>{formatDate(row['Обновлено WB'])}</td>
                        <td>{formatDate(row['Обновлено 1С'])}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="pagination">
            <button 
              onClick={() => setOffset(Math.max(0, offset - limit))} 
              disabled={offset === 0}
            >
              Previous
            </button>
            <span>
              Page {Math.floor(offset / limit) + 1} of {Math.ceil(total / limit)} (Total: {total}, Showing: {data.length})
            </span>
            <button 
              onClick={() => setOffset(offset + limit)} 
              disabled={offset + limit >= total}
            >
              Next
            </button>
          </div>
        </>
      )}
    </div>
  )
}
