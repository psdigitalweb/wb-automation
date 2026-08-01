'use client'

import Link from 'next/link'
import type { MouseEvent } from 'react'
import Icon from './Icon'
import type { RailItemConfig } from './navModel'

type RailNavProps = {
  activePrimary: string
  openPrimary: string
  projectId: string | null
  items: Array<RailItemConfig | { divider: true }>
  collapsed: boolean
  onPrimaryOpen: (id: string) => void
  onCollapsedChange: (collapsed: boolean) => void
}

export default function RailNav({
  activePrimary,
  openPrimary,
  projectId,
  items,
  collapsed,
  onPrimaryOpen,
  onCollapsedChange,
}: RailNavProps) {
  return (
    <aside className="ec-rail" aria-label="Основная навигация">
      <div className="ec-rail-logo">
        <Link className="ec-logo-mark" href="/app/projects" aria-label="EcomCore">
          EC
        </Link>
      </div>
      <nav className="ec-rail-list">
        {items.map((item, index) => {
          if ('divider' in item) return <div key={`divider-${index}`} className="ec-rail-divider" />
          const disabled = Boolean(item.disabled || (item.requiresProject && !projectId))
          const href = item.href(projectId)
          const opensSubNav = Boolean(item.hasSubNav && projectId && !disabled)
          const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
            if (!opensSubNav) return
            event.preventDefault()
            onPrimaryOpen(item.id)
          }
          if (disabled) {
            return (
              <span
                key={item.id}
                className="ec-rail-item is-disabled"
                title={item.label}
                aria-disabled="true"
              >
                <span className="ec-rail-icon-wrap">
                  <Icon name={item.icon} size={18} />
                </span>
                <span className="ec-rail-label">{item.label}</span>
              </span>
            )
          }
          return (
            <Link
              key={item.id}
              className={`ec-rail-item ${activePrimary === item.id ? 'is-active' : ''}`}
              href={href}
              onClick={handleClick}
              title={item.label}
              aria-current={activePrimary === item.id ? 'page' : undefined}
              aria-expanded={opensSubNav ? openPrimary === item.id : undefined}
            >
              <span className="ec-rail-icon-wrap">
                <Icon name={item.icon} size={18} />
              </span>
              <span className="ec-rail-label">{item.label}</span>
            </Link>
          )
        })}
      </nav>
      <button
        type="button"
        className="ec-rail-collapse"
        onClick={() => onCollapsedChange(!collapsed)}
        title={collapsed ? 'Развернуть меню' : 'Свернуть меню'}
        aria-label={collapsed ? 'Развернуть меню' : 'Свернуть меню'}
        aria-pressed={collapsed}
      >
        <Icon name="chevronRight" size={16} />
      </button>
    </aside>
  )
}
