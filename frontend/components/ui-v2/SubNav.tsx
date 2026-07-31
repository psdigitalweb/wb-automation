'use client'

import Link from 'next/link'
import Icon from './Icon'
import type { SubNavGroup } from './navModel'

type SubNavProps = {
  visible: boolean
  projectId: string | null
  restPath: string
  groups: SubNavGroup[]
}

export default function SubNav({ visible, projectId, restPath, groups }: SubNavProps) {
  return (
    <aside className={`ec-subnav ${visible ? 'is-visible' : ''}`} aria-label="Навигация проекта">
      <nav className="ec-subnav-inner">
        {projectId
          ? groups.map((group) => (
              <div className="ec-subnav-group" key={group.id}>
                <div className="ec-subnav-label">{group.label}</div>
                {group.items.map((item) => {
                  const active = item.match(restPath)
                  const expanded = active && Boolean(item.children?.length)
                  const content = (
                    <>
                      <Icon name={item.icon} size={16} />
                      <span>{item.label}</span>
                      {item.badge ? <span className="ec-subnav-badge">{item.badge}</span> : null}
                    </>
                  )
                  if (item.disabled) {
                    return (
                      <span key={item.id} className="ec-subnav-item is-disabled" aria-disabled="true">
                        {content}
                      </span>
                    )
                  }
                  return (
                    <div className="ec-subnav-item-block" key={item.id}>
                      <Link
                        className={`ec-subnav-item ${active ? 'is-active' : ''}`}
                        href={item.href(projectId)}
                        aria-current={active && !expanded ? 'page' : undefined}
                        aria-expanded={expanded ? true : undefined}
                      >
                        {content}
                      </Link>
                      {expanded ? (
                        <div className="ec-subnav-children">
                          {item.children?.map((child) => {
                            const childActive = child.match(restPath)
                            return (
                              <Link
                                key={child.id}
                                className={`ec-subnav-child ${childActive ? 'is-active' : ''}`}
                                href={child.href(projectId)}
                                aria-current={childActive ? 'page' : undefined}
                              >
                                {child.label}
                              </Link>
                            )
                          })}
                        </div>
                      ) : null}
                    </div>
                  )
                })}
              </div>
            ))
          : null}
      </nav>
    </aside>
  )
}
