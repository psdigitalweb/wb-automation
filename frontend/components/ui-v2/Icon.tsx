import type { IconName } from './navModel'

type IconProps = {
  name: IconName
  size?: number
  className?: string
}

const paths: Record<IconName, React.ReactNode> = {
  app: <path d="M4 5.5A1.5 1.5 0 0 1 5.5 4h13A1.5 1.5 0 0 1 20 5.5v13a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 18.5zM8 8h3v3H8zm5 0h3v3h-3zM8 13h3v3H8zm5 0h3v3h-3z" />,
  arrowsDiff: <path d="M16 3h5v5M8 3H3v5M21 3l-7 7M3 3l7 7M3 21l7-7M21 21l-7-7M16 21h5v-5M8 21H3v-5" />,
  bell: <path d="M18 8a6 6 0 1 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" />,
  box: <path d="m12 3 8 4.5v9L12 21l-8-4.5v-9zm0 0v9m8-4.5-8 4.5-8-4.5" />,
  briefcase: <path d="M9 6V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v1m5 5v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-7m16-4H4v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2z" />,
  chart: <path d="M4 19h16M7 16V9m5 7V5m5 11v-4" />,
  chevronRight: <path d="m9 18 6-6-6-6" />,
  coins: <path d="M3 7c0-1.7 3.1-3 7-3s7 1.3 7 3-3.1 3-7 3-7-1.3-7-3zm0 0v5c0 1.7 3.1 3 7 3s7-1.3 7-3V7m-9 8v2c0 1.7 3.1 3 7 3s7-1.3 7-3v-5c0-1-.9-1.9-2.4-2.5" />,
  database: <path d="M5 6c0-1.7 3.1-3 7-3s7 1.3 7 3-3.1 3-7 3-7-1.3-7-3zm0 0v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6" />,
  finance: <path d="M4 19V5m0 14h16M8 16v-5m4 5V8m4 8v-3" />,
  funnel: <path d="M4 5h16l-6.5 7.4V19l-3 1.5v-8.1z" />,
  gear: <path d="M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zm8 4a8 8 0 0 0-.1-1.2l2-1.5-2-3.5-2.4 1a8 8 0 0 0-2-1.2L15.2 3h-4l-.4 2.6a8 8 0 0 0-2 1.2l-2.4-1-2 3.5 2 1.5A8 8 0 0 0 6.4 12c0 .4 0 .8.1 1.2l-2 1.5 2 3.5 2.4-1a8 8 0 0 0 2 1.2l.4 2.6h4l.4-2.6a8 8 0 0 0 2-1.2l2.4 1 2-3.5-2-1.5c.1-.4.1-.8.1-1.2z" />,
  home: <path d="m4 11 8-7 8 7v8a1 1 0 0 1-1 1h-5v-6h-4v6H5a1 1 0 0 1-1-1z" />,
  imageOff: <path d="M4 16.5V5a1 1 0 0 1 1-1h11.5M20 8v11a1 1 0 0 1-1 1H8m-4-4 4-4 3 3 2-2 7 7M14 8.5a2.5 2.5 0 0 1 1.5-2.3M3 3l18 18" />,
  inbox: <path d="M22 12h-6l-2 3h-4l-2-3H2m3.5-6.5L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.5A2 2 0 0 0 16.8 4H7.2a2 2 0 0 0-1.7 1.5z" />,
  layout: <path d="M3 5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zm6-2v18M3 9h18" />,
  logout: <path d="M10 5H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h4m5-4 4-4-4-4m4 4H9" />,
  mapPin: <path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0zm-8-3a3 3 0 1 0 0 6 3 3 0 0 0 0-6" />,
  network: <path d="M9 5a3 3 0 1 1-6 0 3 3 0 0 1 6 0zm12 0a3 3 0 1 1-6 0 3 3 0 0 1 6 0zM15 19a3 3 0 1 1-6 0 3 3 0 0 1 6 0zM8.5 7l2 9m5-9-2 9M9 5h6" />,
  package: <path d="m12 3 8 4.5v9L12 21l-8-4.5v-9zm0 0v9m8-4.5-8 4.5-8-4.5" />,
  percent: <path d="M19 5 5 19M7 5a2 2 0 1 1-4 0 2 2 0 0 1 4 0zm14 14a2 2 0 1 1-4 0 2 2 0 0 1 4 0z" />,
  puzzle: <path d="M3 3h7v7H3zm11 0h7v7h-7zm0 11h7v7h-7zM3 14h7v7H3z" />,
  settings: <path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zm7-3.5a7 7 0 0 0-.1-1l2-1.6-2-3.4-2.5 1a7 7 0 0 0-1.7-1L14.3 3h-4.6l-.4 3a7 7 0 0 0-1.7 1l-2.5-1-2 3.4 2 1.6a7 7 0 0 0 0 2l-2 1.6 2 3.4 2.5-1a7 7 0 0 0 1.7 1l.4 3h4.6l.4-3a7 7 0 0 0 1.7-1l2.5 1 2-3.4-2-1.6c.1-.3.1-.7.1-1z" />,
  spark: <path d="m12 3 1.7 5.2L19 10l-5.3 1.8L12 17l-1.7-5.2L5 10l5.3-1.8zM19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z" />,
  store: <path d="M5 10h14l-1-5H6zm1 0v9h12v-9M9 19v-5h6v5" />,
  user: <path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm7 8a7 7 0 0 0-14 0" />,
  wb: <path d="M4 6h3l1.3 8L11 6h2l2.7 8L17 6h3l-2.4 12h-3L12 10.5 9.4 18h-3z" />,
}

export default function Icon({ name, size = 16, className }: IconProps) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {paths[name]}
    </svg>
  )
}
