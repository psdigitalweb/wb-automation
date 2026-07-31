'use client'

import { useRouter } from 'next/navigation'

interface PortalBackButtonProps {
  fallbackHref: string
  label?: string
}

export default function PortalBackButton({ fallbackHref, label = '← Назад' }: PortalBackButtonProps) {
  const router = useRouter()

  const handleClick = () => {
    if (typeof window !== 'undefined' && window.history.length > 1) {
      router.back()
    } else {
      router.push(fallbackHref)
    }
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      style={{
        background: 'none',
        border: 'none',
        padding: 0,
        font: 'inherit',
        color: '#2563eb',
        cursor: 'pointer',
        textDecoration: 'none',
      }}
    >
      {label}
    </button>
  )
}
