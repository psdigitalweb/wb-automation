'use client'

import { useState, useEffect, useRef } from 'react'

interface CategoryOption {
  id: number
  name: string | null
}

interface CategoryMultiSelectPopoverProps {
  categories: CategoryOption[]
  selectedIds: number[]
  onChange: (ids: number[]) => void
}

export default function CategoryMultiSelectPopover({
  categories,
  selectedIds,
  onChange,
}: CategoryMultiSelectPopoverProps) {
  const [open, setOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const popoverRef = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)

  // Filter categories by search query (client-side)
  const filteredCategories = categories.filter((cat) => {
    if (!searchQuery.trim()) return true
    const query = searchQuery.toLowerCase()
    const name = (cat.name || `ID ${cat.id}`).toLowerCase()
    return name.includes(query)
  })

  // Close popover on click outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (!open) return
      const target = event.target as Node
      if (
        popoverRef.current &&
        !popoverRef.current.contains(target) &&
        buttonRef.current &&
        !buttonRef.current.contains(target)
      ) {
        setOpen(false)
        setSearchQuery('')
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [open])

  // Close popover on Escape
  useEffect(() => {
    function handleEscape(event: KeyboardEvent) {
      if (event.key === 'Escape' && open) {
        setOpen(false)
        setSearchQuery('')
      }
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [open])

  const handleToggle = (id: number) => {
    const newIds = selectedIds.includes(id)
      ? selectedIds.filter((x) => x !== id)
      : [...selectedIds, id]
    onChange(newIds)
  }

  const handleClear = () => {
    onChange([])
    setSearchQuery('')
  }

  const selectedCount = selectedIds.length
  const buttonText =
    selectedCount === 0 ? 'Категории: Все' : `Категории: ${selectedCount} выбрано`

  return (
    <div style={{ position: 'relative', display: 'inline-block' }}>
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen(!open)}
        style={{
          padding: '6px 12px',
          border: '1px solid #d1d5db',
          borderRadius: 6,
          background: '#fff',
          color: '#111827',
          fontSize: 14,
          cursor: 'pointer',
          fontWeight: selectedCount > 0 ? 500 : 400,
          transition: 'all 0.2s',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.borderColor = '#9ca3af'
          e.currentTarget.style.backgroundColor = '#f9fafb'
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.borderColor = '#d1d5db'
          e.currentTarget.style.backgroundColor = '#fff'
        }}
      >
        {buttonText}
      </button>

      {open && (
        <div
          ref={popoverRef}
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            marginTop: 8,
            zIndex: 1000,
            background: '#fff',
            border: '1px solid #d1d5db',
            borderRadius: 8,
            boxShadow: '0 4px 16px rgba(0,0,0,0.12)',
            minWidth: 280,
            maxWidth: 400,
            overflow: 'hidden',
          }}
        >
          {/* Search input */}
          <div style={{ padding: 12, borderBottom: '1px solid #e5e7eb' }}>
            <input
              type="text"
              placeholder="Поиск категорий..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{
                width: '100%',
                padding: '6px 10px',
                border: '1px solid #d1d5db',
                borderRadius: 4,
                fontSize: 14,
              }}
              autoFocus
            />
          </div>

          {/* Scrollable list */}
          <div
            style={{
              maxHeight: 300,
              overflowY: 'auto',
              padding: 4,
            }}
          >
            {filteredCategories.length === 0 ? (
              <div
                style={{
                  padding: 16,
                  textAlign: 'center',
                  color: '#6b7280',
                  fontSize: 14,
                }}
              >
                {searchQuery ? 'Категории не найдены' : 'Нет категорий'}
              </div>
            ) : (
              filteredCategories.map((cat) => {
                const isSelected = selectedIds.includes(cat.id)
                const displayName = cat.name || `ID ${cat.id}`
                return (
                  <label
                    key={cat.id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      padding: '8px 12px',
                      cursor: 'pointer',
                      borderRadius: 4,
                      transition: 'background-color 0.15s',
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.backgroundColor = '#f3f4f6'
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.backgroundColor = 'transparent'
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => handleToggle(cat.id)}
                      style={{
                        width: 16,
                        height: 16,
                        cursor: 'pointer',
                      }}
                    />
                    <span style={{ fontSize: 14, color: '#111827', flex: 1 }}>
                      {displayName}
                    </span>
                  </label>
                )
              })
            )}
          </div>

          {/* Clear button */}
          {selectedCount > 0 && (
            <div
              style={{
                padding: 8,
                borderTop: '1px solid #e5e7eb',
                display: 'flex',
                justifyContent: 'flex-end',
              }}
            >
              <button
                type="button"
                onClick={handleClear}
                style={{
                  padding: '4px 12px',
                  border: '1px solid #d1d5db',
                  borderRadius: 4,
                  background: '#fff',
                  color: '#374151',
                  fontSize: 13,
                  cursor: 'pointer',
                  transition: 'all 0.15s',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = '#9ca3af'
                  e.currentTarget.style.backgroundColor = '#f9fafb'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = '#d1d5db'
                  e.currentTarget.style.backgroundColor = '#fff'
                }}
              >
                Сбросить
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
