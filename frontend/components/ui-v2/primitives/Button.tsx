import type { ButtonHTMLAttributes, ReactNode } from 'react'

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md' | 'lg' | 'icon'
}

export function Button({ children, variant = 'secondary', size = 'md', className = '', ...props }: ButtonProps) {
  return (
    <button className={`ec-button ec-button-${variant} ec-button-${size} ${className}`.trim()} {...props}>
      {children}
    </button>
  )
}

