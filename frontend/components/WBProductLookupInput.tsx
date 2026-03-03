'use client'

import React, { useEffect, useMemo, useRef, useState } from 'react'
import { getWBProductLookup, type WBProductLookupItem } from '@/lib/apiClient'

type Props = {
  projectId: string
  value: string
  onChange: (value: string) => void
  onSelect: (item: WBProductLookupItem) => void
  placeholder?: string
  className?: string
}

function formatPrimary(item: WBProductLookupItem): string {
  return item.vendor_code ? `${item.vendor_code} · ${item.nm_id}` : String(item.nm_id)
}

export default function WBProductLookupInput({
  projectId,
  value,
  onChange,
  onSelect,
  placeholder,
  className,
}: Props) {
  const [items, setItems] = useState<WBProductLookupItem[]>([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const requestSeqRef = useRef(0)
  const closeTimerRef = useRef<number | null>(null)

  const trimmedValue = useMemo(() => value.trim(), [value])

  useEffect(() => {
    if (!projectId || trimmedValue.length < 1) {
      setItems([])
      setOpen(false)
      return
    }

    const requestId = ++requestSeqRef.current
    const timer = window.setTimeout(async () => {
      try {
        setLoading(true)
        const res = await getWBProductLookup(projectId, { q: trimmedValue, limit: 8 })
        if (requestId !== requestSeqRef.current) return
        setItems(res.items)
        setOpen(res.items.length > 0)
      } catch {
        if (requestId !== requestSeqRef.current) return
        setItems([])
        setOpen(false)
      } finally {
        if (requestId === requestSeqRef.current) setLoading(false)
      }
    }, 180)

    return () => {
      window.clearTimeout(timer)
    }
  }, [projectId, trimmedValue])

  useEffect(() => {
    return () => {
      if (closeTimerRef.current != null) {
        window.clearTimeout(closeTimerRef.current)
      }
    }
  }, [])

  return (
    <div style={{ position: 'relative', width: '100%', minWidth: 0 }}>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => {
          if (items.length > 0) setOpen(true)
        }}
        onBlur={() => {
          closeTimerRef.current = window.setTimeout(() => setOpen(false), 120)
        }}
        placeholder={placeholder}
        className={`h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm leading-5 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 placeholder:text-gray-400 ${className || ''}`.trim()}
        autoComplete="off"
        style={{
          width: '100%',
          minWidth: 0,
          boxSizing: 'border-box',
        }}
      />
      {open && (
        <div
          style={{
            position: 'absolute',
            top: 'calc(100% + 4px)',
            left: 0,
            right: 0,
            zIndex: 20,
            background: '#fff',
            border: '1px solid #d1d5db',
            borderRadius: 8,
            boxShadow: '0 10px 24px rgba(0,0,0,0.12)',
            maxHeight: 320,
            overflowY: 'auto',
          }}
        >
          {items.map((item) => (
            <button
              key={item.nm_id}
              type="button"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => {
                onSelect(item)
                setOpen(false)
              }}
              style={{
                width: '100%',
                textAlign: 'left',
                padding: '10px 12px',
                border: 0,
                background: '#fff',
                cursor: 'pointer',
                borderBottom: '1px solid #f3f4f6',
              }}
            >
              <div style={{ fontSize: 13, fontWeight: 600 }}>{formatPrimary(item)}</div>
              {(item.title || item.wb_category) && (
                <div style={{ marginTop: 2, fontSize: 12, color: '#6b7280' }}>
                  {item.title || '—'}
                  {item.wb_category ? ` · ${item.wb_category}` : ''}
                </div>
              )}
            </button>
          ))}
          {loading && items.length === 0 && (
            <div style={{ padding: '10px 12px', fontSize: 12, color: '#6b7280' }}>Поиск…</div>
          )}
        </div>
      )}
    </div>
  )
}
