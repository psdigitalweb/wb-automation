export type IconName =
  | 'app'
  | 'arrowsDiff'
  | 'bell'
  | 'briefcase'
  | 'box'
  | 'chart'
  | 'chevronRight'
  | 'coins'
  | 'database'
  | 'finance'
  | 'funnel'
  | 'gear'
  | 'home'
  | 'imageOff'
  | 'inbox'
  | 'layout'
  | 'logout'
  | 'mapPin'
  | 'network'
  | 'package'
  | 'percent'
  | 'puzzle'
  | 'settings'
  | 'spark'
  | 'store'
  | 'user'
  | 'wb'

export type RailItemConfig = {
  id: string
  label: string
  icon: IconName
  href: (projectId: string | null) => string
  match: (pathname: string) => boolean
  hasSubNav?: boolean
  requiresProject?: boolean
  disabled?: boolean
  marketplaceCode?: 'wildberries' | 'ozon'
}

export type SubNavItemConfig = {
  id: string
  label: string
  icon: IconName
  href: (projectId: string) => string
  match: (restPath: string) => boolean
  badge?: string
  disabled?: boolean
  marketplaceCode?: 'wildberries' | 'ozon'
  children?: Array<Omit<SubNavItemConfig, 'icon' | 'children'>>
}

export type SubNavGroup = {
  id: string
  label: string
  items: SubNavItemConfig[]
}

export const railItems: Array<RailItemConfig | { divider: true }> = [
  {
    id: 'overview',
    label: 'Обзор',
    icon: 'layout',
    href: (projectId) => (projectId ? `/app/project/${projectId}/dashboard` : '/app/projects'),
    match: (pathname) => /^\/app\/project\/\d+\/dashboard\/?$/.test(pathname),
    requiresProject: true,
  },
  {
    id: 'wb',
    label: 'WB',
    icon: 'box',
    href: (projectId) => (projectId ? `/app/project/${projectId}/wildberries` : '/app/projects'),
    match: (pathname) =>
      /^\/app\/project\/\d+\/wildberries(?:\/|$)/.test(pathname) &&
      !/^\/app\/project\/\d+\/wildberries\/hypothesis-lab(?:\/|$)/.test(pathname),
    requiresProject: true,
    hasSubNav: true,
    marketplaceCode: 'wildberries',
  },
  {
    id: 'ozon',
    label: 'Ozon',
    icon: 'box',
    href: (projectId) => (projectId ? `/app/project/${projectId}/marketplaces` : '/app/projects'),
    match: (pathname) => /^\/app\/project\/\d+\/ozon(?:\/|$)/.test(pathname),
    requiresProject: true,
    hasSubNav: true,
    marketplaceCode: 'ozon',
  },
  {
    id: 'modules',
    label: 'Модули',
    icon: 'puzzle',
    href: (projectId) => (projectId ? `/app/project/${projectId}/seo` : '/app/projects'),
    match: (pathname) =>
      /^\/app\/project\/\d+\/(seo|competitor-reviews|wildberries\/hypothesis-lab|tests|supplies|design)(?:\/|$)/.test(pathname),
    requiresProject: true,
    hasSubNav: true,
  },
  { divider: true },
  {
    id: 'compare',
    label: 'Цены',
    icon: 'arrowsDiff',
    href: (projectId) => (projectId ? `/app/project/${projectId}/wildberries/price-discrepancies` : '/app/projects'),
    match: () => false,
    requiresProject: true,
    disabled: true,
  },
  {
    id: 'inbox',
    label: 'Сигналы',
    icon: 'bell',
    href: (projectId) => (projectId ? `/app/project/${projectId}/wildberries/funnel-signals` : '/app/projects'),
    match: () => false,
    requiresProject: true,
    disabled: true,
  },
  {
    id: 'expenses',
    label: 'Расходы',
    icon: 'coins',
    href: (projectId) => (projectId ? `/app/project/${projectId}/additional-costs` : '/app/projects'),
    match: () => false,
    requiresProject: true,
  },
  { divider: true },
  {
    id: 'settings',
    label: 'Настр.',
    icon: 'settings',
    href: (projectId) => (projectId ? `/app/project/${projectId}/settings` : '/app/projects'),
    match: (pathname) =>
      /^\/app\/project\/\d+\/(settings|members|marketplaces|internal-data\/settings|ingestion|cogs|additional-costs)(?:\/|$)/.test(pathname),
    requiresProject: true,
    hasSubNav: true,
  },
]

export const subNavGroupsByRail: Record<string, SubNavGroup[]> = {
  wb: [
    {
      id: 'data',
      label: 'Данные',
      items: [
        {
          id: 'catalog',
          label: 'Каталог',
          icon: 'package',
          href: (projectId) => `/app/project/${projectId}/wildberries/catalog`,
          match: (rest) => rest.startsWith('wildberries/catalog'),
        },
        {
          id: 'prices',
          label: 'Цены',
          icon: 'coins',
          href: (projectId) => `/app/project/${projectId}/wildberries/price-analytics`,
          match: (rest) => rest.startsWith('wildberries/price-analytics'),
        },
        {
          id: 'stocks',
          label: 'Остатки',
          icon: 'database',
          href: () => '#',
          match: () => false,
          disabled: true,
        },
      ],
    },
    {
      id: 'reports',
      label: 'Отчеты',
      items: [
        {
          id: 'funnel',
          label: 'Воронка',
          icon: 'funnel',
          href: (projectId) => `/app/project/${projectId}/wildberries/funnel-signals`,
          match: (rest) => rest.startsWith('wildberries/funnel-signals'),
        },
        {
          id: 'spp-dynamics',
          label: 'Динамика СПП',
          icon: 'percent',
          href: (projectId) => `/app/project/${projectId}/wildberries/spp-dynamics`,
          match: (rest) => rest.startsWith('wildberries/spp-dynamics'),
        },
        {
          id: 'product-groups',
          label: 'Аналитика связок',
          icon: 'network',
          href: (projectId) => `/app/project/${projectId}/wildberries/product-groups`,
          match: (rest) => rest.startsWith('wildberries/product-groups'),
        },
        {
          id: 'unit-pnl',
          label: 'Unit PNL',
          icon: 'finance',
          href: (projectId) => `/app/project/${projectId}/wildberries/finances/unit-pnl`,
          match: (rest) => rest.startsWith('wildberries/finances/unit-pnl'),
        },
        {
          id: 'sales-trends',
          label: 'Динамика продаж',
          icon: 'chart',
          href: (projectId) => `/app/project/${projectId}/wildberries/sales-trends`,
          match: (rest) => rest.startsWith('wildberries/sales-trends'),
        },
        {
          id: 'geo-sales',
          label: 'Гео продаж',
          icon: 'mapPin',
          href: (projectId) => `/app/project/${projectId}/wildberries/order-geography`,
          match: (rest) => rest.startsWith('wildberries/order-geography'),
        },
        {
          id: 'without-photos',
          label: 'Остаток без фото',
          icon: 'imageOff',
          href: (projectId) => `/app/project/${projectId}/wildberries/stock-without-photos`,
          match: (rest) => rest.startsWith('wildberries/stock-without-photos'),
        },
        {
          id: 'reviews',
          label: 'Отзывы',
          icon: 'inbox',
          href: (projectId) => `/app/project/${projectId}/wildberries/reviews`,
          match: (rest) => rest.startsWith('wildberries/reviews'),
        },
      ],
    },
  ],
  ozon: [
    {
      id: 'ozon',
      label: 'Ozon',
      items: [
        {
          id: 'marketplace',
          label: 'Подключение',
          icon: 'store',
          href: (projectId) => `/app/project/${projectId}/marketplaces`,
          match: (rest) => rest.startsWith('marketplaces'),
        },
      ],
    },
  ],
  modules: [
    {
      id: 'modules',
      label: 'Модули',
      items: [
        {
          id: 'seo',
          label: 'SEO WB',
          icon: 'spark',
          href: (projectId) => `/app/project/${projectId}/seo`,
          match: (rest) => rest.startsWith('seo'),
          marketplaceCode: 'wildberries',
          children: [
            {
              id: 'seo-dashboard',
              label: 'Дашборд',
              href: (projectId) => `/app/project/${projectId}/seo`,
              match: (rest) => rest === 'seo',
            },
            {
              id: 'seo-categories',
              label: 'Категории',
              href: (projectId) => `/app/project/${projectId}/seo/categories`,
              match: (rest) => rest.startsWith('seo/categories'),
            },
            {
              id: 'seo-products',
              label: 'Товары',
              href: (projectId) => `/app/project/${projectId}/seo/products`,
              match: (rest) => rest.startsWith('seo/products'),
            },
            {
              id: 'seo-inbox',
              label: 'Подборы',
              href: (projectId) => `/app/project/${projectId}/seo/products?status=review`,
              match: () => false,
            },
          ],
        },
        {
          id: 'hypotheses',
          label: 'Гипотезы',
          icon: 'spark',
          href: (projectId) => `/app/project/${projectId}/wildberries/hypothesis-lab/experiments`,
          match: (rest) => rest.startsWith('wildberries/hypothesis-lab'),
        },
        {
          id: 'competitor-reviews',
          label: 'Отзывы конкурентов',
          icon: 'inbox',
          href: (projectId) => `/app/project/${projectId}/competitor-reviews`,
          match: (rest) => rest.startsWith('competitor-reviews'),
        },
        {
          id: 'tests',
          label: 'Тесты',
          icon: 'app',
          href: () => '#',
          match: () => false,
          disabled: true,
        },
        {
          id: 'supplies',
          label: 'Поставки',
          icon: 'package',
          href: () => '#',
          match: () => false,
          disabled: true,
        },
        {
          id: 'design',
          label: 'Оформление',
          icon: 'layout',
          href: () => '#',
          match: () => false,
          disabled: true,
        },
      ],
    },
  ],
  settings: [
    {
      id: 'project',
      label: 'Проект',
      items: [
        {
          id: 'overview',
          label: 'Общее',
          icon: 'settings',
          href: (projectId) => `/app/project/${projectId}/settings`,
          match: () => false,
        },
        {
          id: 'members',
          label: 'Пользователи',
          icon: 'user',
          href: (projectId) => `/app/project/${projectId}/members`,
          match: (rest) => rest.startsWith('members'),
        },
      ],
    },
    {
      id: 'data',
      label: 'Данные',
      items: [
        {
          id: 'data-loading',
          label: 'Загрузка данных',
          icon: 'database',
          href: (projectId) => `/app/project/${projectId}/settings`,
          match: (rest) => rest === 'settings',
        },
        {
          id: 'ingestion-schedule',
          label: 'Расписание загрузки',
          icon: 'chart',
          href: (projectId) => `/app/project/${projectId}/ingestion`,
          match: (rest) => rest.startsWith('ingestion'),
        },
        {
          id: 'catalog-settings',
          label: 'Загрузка каталога',
          icon: 'database',
          href: (projectId) => `/app/project/${projectId}/internal-data/settings`,
          match: (rest) => rest.startsWith('internal-data/settings'),
        },
        {
          id: 'data-availability',
          label: 'Наличие данных',
          icon: 'chart',
          href: (projectId) => `/app/project/${projectId}/settings/data-availability`,
          match: (rest) => rest.startsWith('settings/data-availability'),
        },
      ],
    },
    {
      id: 'finance',
      label: 'Финансы',
      items: [
        {
          id: 'cogs',
          label: 'Себестоимость',
          icon: 'database',
          href: (projectId) => `/app/project/${projectId}/cogs`,
          match: (rest) => rest.startsWith('cogs'),
        },
        {
          id: 'expenses',
          label: 'Расходы',
          icon: 'coins',
          href: (projectId) => `/app/project/${projectId}/additional-costs`,
          match: (rest) => rest.startsWith('additional-costs'),
        },
        {
          id: 'taxes',
          label: 'Налоги',
          icon: 'coins',
          href: (projectId) => `/app/project/${projectId}/settings/taxes`,
          match: (rest) => rest.startsWith('settings/taxes'),
        },
      ],
    },
    {
      id: 'integrations',
      label: 'Интеграции',
      items: [
        {
          id: 'marketplaces',
          label: 'Подключение МП',
          icon: 'store',
          href: (projectId) => `/app/project/${projectId}/marketplaces`,
          match: (rest) => rest.startsWith('marketplaces'),
        },
        {
          id: 'proxy',
          label: 'Прокси',
          icon: 'settings',
          href: (projectId) => `/app/project/${projectId}/settings/proxy`,
          match: (rest) => rest.startsWith('settings/proxy'),
        },
      ],
    },
  ],
}

export function filterRailItemsByMarketplaces(
  items: Array<RailItemConfig | { divider: true }>,
  connectedMarketplaces: Set<string> | null,
): Array<RailItemConfig | { divider: true }> {
  return items.filter((item) => {
    if ('divider' in item) return true
    if (!item.marketplaceCode) return true
    if (connectedMarketplaces === null) return false
    return connectedMarketplaces.has(item.marketplaceCode)
  })
}

export function filterSubNavGroupsByMarketplaces(
  groups: SubNavGroup[],
  connectedMarketplaces: Set<string> | null,
): SubNavGroup[] {
  return groups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => {
        if (!item.marketplaceCode) return true
        if (connectedMarketplaces === null) return false
        return connectedMarketplaces.has(item.marketplaceCode)
      }),
    }))
    .filter((group) => group.items.length > 0)
}

export function getProjectRoute(pathname: string): { projectId: string | null; restPath: string } {
  const match = pathname.match(/^\/app\/project\/(\d+)(?:\/(.*))?$/)
  return {
    projectId: match?.[1] ?? null,
    restPath: match?.[2] ?? '',
  }
}

export function getActiveRailId(pathname: string): string {
  const active = railItems.find((item) => 'id' in item && item.match(pathname))
  return active && 'id' in active ? active.id : 'projects'
}

export function humanizeSegment(segment: string): string {
  const known: Record<string, string> = {
    app: 'Приложение',
    project: 'Проект',
    projects: 'Проекты',
    dashboard: 'Дашборд',
    wildberries: 'Wildberries',
    finances: 'Финансы',
    reports: 'Отчеты',
    'unit-pnl': 'Юнит-экономика',
    'sku-pnl': 'SKU PnL',
    'content-analytics': 'Аналитика карточек',
    catalog: 'Каталог товаров',
    reviews: 'Отзывы',
    'funnel-signals': 'Воронка',
    'product-groups': 'Аналитика связок',
    'search-report': 'Поисковые запросы',
    'price-discrepancies': 'Расхождения цен',
    'price-analytics': 'Аналитика цен',
    'stock-without-photos': 'Товары без фото',
    settings: 'Настройки',
    members: 'Участники',
    marketplaces: 'Маркетплейсы',
    'internal-data': 'Внутренние данные',
    categories: 'Категории',
    prices: 'Цены',
    stocks: 'Остатки',
    'supplier-stocks': 'Склады поставщика',
    'rrp-snapshots': 'РРЦ',
    'frontend-prices': 'Цены на витрине',
    ingestion: 'Загрузки',
    cogs: 'Себестоимость',
    'additional-costs': 'Расходы',
    'competitor-reviews': 'Анализ отзывов конкурентов',
  }

  return known[segment] ?? segment.replace(/-/g, ' ').replace(/^\w/, (char) => char.toUpperCase())
}
