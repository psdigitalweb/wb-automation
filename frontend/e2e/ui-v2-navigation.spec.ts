import { expect, test } from '@playwright/test'

const project = {
  id: 1,
  name: 'Intro-Version',
  description: null,
  created_by: 1,
  created_at: '2026-01-27T00:00:00Z',
  updated_at: '2026-01-27T00:00:00Z',
  role: 'owner',
  members: [],
}

const dashboardKpis = {
  wb: {
    products_total: 847,
    warehouses_fbs_total: 2,
  },
  stock: {
    fbs_in_stock_products: 128,
    fbo_in_stock_products: 64,
  },
  prices: {
    wb_prices_products: 812,
  },
  storefront: {
    storefront_products: 790,
    expected_storefront_products: 847,
  },
  rrp_xml: {
    total: 840,
    with_price: 820,
    with_stock: 760,
    with_price_and_stock: 740,
  },
  internal_data: {
    total: 845,
    with_stock: 801,
  },
  last_snapshots: {
    fbs_stock_at: '2026-01-27T10:15:00Z',
    fbo_stock_at: '2026-01-27T10:16:00Z',
    wb_prices_at: '2026-01-27T10:17:00Z',
    storefront_at: '2026-01-27T10:18:00Z',
    rrp_at: '2026-01-27T10:19:00Z',
    internal_data_at: '2026-01-27T10:20:00Z',
  },
}

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/**', (route) => {
    const pathname = new URL(route.request().url()).pathname

    if (pathname === '/api/v1/projects') {
      return route.fulfill({ json: [project] })
    }

    if (pathname === '/api/v1/projects/1/marketplaces') {
      return route.fulfill({
        json: [
          {
            id: 1,
            marketplace_id: 1,
            marketplace_code: 'wildberries',
            marketplace_name: 'Wildberries',
            is_enabled: true,
          },
          {
            id: 2,
            marketplace_id: 2,
            marketplace_code: 'ozon',
            marketplace_name: 'Ozon',
            is_enabled: false,
          },
        ],
      })
    }

    if (pathname === '/api/v1/projects/1') {
      return route.fulfill({ json: project })
    }

    if (pathname === '/api/v1/dashboard/projects/1/kpis') {
      return route.fulfill({ json: dashboardKpis })
    }

    if (pathname === '/api/v1/projects/1/wildberries/price-discrepancies') {
      return route.fulfill({
        json: {
          items: [],
          meta: {
            total_count: 3,
          },
        },
      })
    }

    if (pathname === '/api/v1/projects/1/marketplaces/wildberries/finances/reports/latest') {
      return route.fulfill({
        json: {
          report_id: 42,
          period_from: '2026-01-20',
          period_to: '2026-01-26',
          currency: 'RUB',
          total_amount: null,
          rows_count: 12,
          first_seen_at: '2026-01-27T10:00:00Z',
          last_seen_at: '2026-01-27T10:20:00Z',
        },
      })
    }

    if (pathname === '/api/v1/projects/1/cogs/coverage') {
      return route.fulfill({
        json: {
          internal_data_available: true,
          internal_skus_total: 10,
          covered_total: 7,
          missing_total: 3,
          coverage_pct: 70,
        },
      })
    }

    if (pathname === '/api/v1/projects/1/cogs/price-sources') {
      return route.fulfill({ json: { available_sources: [] } })
    }

    if (pathname === '/api/v1/projects/1/cogs/direct-rules') {
      return route.fulfill({ json: { items: [], total: 0 } })
    }

    if (pathname === '/api/v1/projects/1/cogs/missing-skus') {
      return route.fulfill({ json: { items: [], total: 0 } })
    }

    if (pathname.startsWith('/api/v1/projects/1/additional-costs/')) {
      if (pathname.endsWith('/summary')) return route.fulfill({ json: { total_amount: 0, by_category: [] } })
      if (pathname.endsWith('/entries')) return route.fulfill({ json: { items: [], total: 0 } })
      if (pathname.endsWith('/categories')) return route.fulfill({ json: { categories: [] } })
    }

    if (pathname.startsWith('/api/v1/projects/1/warehouse-labor/')) {
      if (pathname.endsWith('/summary')) return route.fulfill({ json: { total_amount: 0 } })
      if (pathname.endsWith('/days')) return route.fulfill({ json: { items: [], total: 0 } })
    }

    if (pathname.startsWith('/api/v1/projects/1/packaging/')) {
      if (pathname.endsWith('/summary')) return route.fulfill({ json: { total_amount: 0 } })
      if (pathname.endsWith('/tariffs')) return route.fulfill({ json: { items: [], total: 0 } })
    }

    if (pathname === '/api/v1/projects/1/settings/proxy') {
      return route.fulfill({
        json: {
          enabled: true,
          scheme: 'http',
          host: 'proxy.example.test',
          port: 8080,
          username: null,
          rotate_mode: 'fixed',
          test_url: 'https://example.test',
          last_test_at: '2026-01-27T10:20:00Z',
          last_test_ok: true,
          last_test_error: null,
          password_set: true,
        },
      })
    }

    if (pathname === '/api/v1/projects/1/ingestions/wb/status') {
      return route.fulfill({
        json: [
          {
            job_code: 'frontend_prices',
            title: 'Витринные цены',
            has_schedule: true,
            schedule_summary: 'каждый день',
            last_run_at: '2026-01-27T10:20:00Z',
            last_status: 'success',
            is_running: false,
          },
          {
            job_code: 'wb_card_stats_daily',
            title: 'Воронка',
            has_schedule: false,
            schedule_summary: null,
            last_run_at: null,
            last_status: null,
            is_running: false,
          },
        ],
      })
    }

    return route.fulfill({ json: [] })
  })
  await page.addInitScript(() => {
    localStorage.setItem('ecomcore.ui', 'v2')
    localStorage.setItem('wb_access_token', 'playwright-token')
    localStorage.setItem('wb_refresh_token', 'playwright-refresh')
    localStorage.setItem(
      'wb_user',
      JSON.stringify({
        id: 1,
        username: 'admin',
        email: 'admin@example.test',
        is_active: true,
        is_superuser: true,
      }),
    )
  })
})

test.describe('UI v2 navigation contract', () => {
  test('opens subnav rails without redirecting and keeps Ozon hidden when disconnected', async ({ page }) => {
    await page.goto('/app/project/1/seo?ui=v2', { waitUntil: 'domcontentloaded' })

    await expect(page.locator('.ec-rail-item', { hasText: 'Модули' })).toHaveClass(/is-active/)
    await expect(page.locator('.ec-subnav-item.is-active', { hasText: 'SEO' })).toBeVisible()
    await expect(page.locator('.ec-rail-item', { hasText: 'Ozon' })).toHaveCount(0)
    await expect(page.locator('.ec-rail-item', { hasText: 'Цены' })).toHaveAttribute('aria-disabled', 'true')
    await expect(page.locator('.ec-rail-item', { hasText: 'Сигналы' })).toHaveAttribute('aria-disabled', 'true')
    await expect(page.getByRole('link', { name: 'Цены' })).toHaveCount(0)
    await expect(page.getByRole('link', { name: 'Сигналы' })).toHaveCount(0)

    await page.locator('.ec-subnav-item', { hasText: 'Гипотезы' }).click()
    await expect(page).toHaveURL(/\/app\/project\/1\/wildberries\/hypothesis-lab\/experiments$/)
    await expect(page.getByText(/redirect|перенаправ/i)).toHaveCount(0)

    await page.goto('/app/project/1/seo?ui=v2', { waitUntil: 'domcontentloaded' })
    const wbRail = page.locator('.ec-rail-item', { hasText: 'WB' })
    await wbRail.click()
    await expect(page).toHaveURL(/\/app\/project\/1\/seo\?ui=v2$/)
    await expect(page.locator('.ec-subnav-label', { hasText: 'Отчеты' })).toBeVisible()

    const settingsRail = page.locator('.ec-rail-item', { hasText: 'Настр.' })
    await settingsRail.click()
    await expect(page).toHaveURL(/\/app\/project\/1\/seo\?ui=v2$/)
    await expect(page.locator('.ec-subnav-item', { hasText: 'Подключение МП' })).toHaveAttribute(
      'href',
      '/app/project/1/marketplaces',
    )
  })

  test('marks the requested routes with the correct rail active state', async ({ page }) => {
    await page.goto('/app/project/1/wildberries?ui=v2', { waitUntil: 'domcontentloaded' })
    await expect(page.locator('.ec-rail-item.is-active')).toHaveText(/WB/)

    const wbRoutes = [
      ['/app/project/1/wildberries/price-analytics?ui=v2', /Цены/],
      ['/app/project/1/wildberries/stock-without-photos?ui=v2', /Без фото/],
      ['/app/project/1/wildberries/finances/unit-pnl?ui=v2', /Unit PNL/],
      ['/app/project/1/wildberries/funnel-signals?ui=v2', /Воронка/],
      ['/app/project/1/wildberries/reviews?ui=v2', /Отзывы/],
    ] as const

    for (const [route, activeSubnav] of wbRoutes) {
      await page.goto(route, { waitUntil: 'domcontentloaded' })
      await expect(page.locator('.ec-rail-item.is-active')).toHaveText(/WB/)
      await expect(page.locator('.ec-subnav-item.is-active')).toHaveText(activeSubnav)
    }

    await page.goto('/app/project/1/wildberries/hypothesis-lab/experiments?ui=v2', { waitUntil: 'domcontentloaded' })
    await expect(page.locator('.ec-rail-item.is-active')).toHaveText(/Модули/)
    await expect(page.locator('.ec-subnav-item.is-active')).toHaveText(/Гипотезы/)

    await page.goto('/app/project/1/seo?ui=v2', { waitUntil: 'domcontentloaded' })
    await expect(page.locator('.ec-rail-item.is-active')).toHaveText(/Модули/)
    await expect(page.locator('.ec-subnav-item.is-active')).toHaveText(/SEO/)

    await page.goto('/app/project/1/settings?ui=v2', { waitUntil: 'domcontentloaded' })
    await expect(page.locator('.ec-rail-item.is-active')).toHaveText(/Настр\./)
    await expect(page.locator('.ec-subnav-item.is-active')).toHaveText(/Загрузка данных/)
    await expect(page.getByRole('heading', { name: 'Настройки проекта Intro-Version' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Загрузка данных WB' })).toBeVisible()
    await expect(page.locator('.ec-subnav-label', { hasText: 'Проект' })).toBeVisible()
    await expect(page.locator('.ec-subnav-item', { hasText: 'Общее' })).toBeVisible()
    await expect(page.locator('.ec-subnav-item', { hasText: 'Пользователи' })).toBeVisible()
    await expect(page.locator('.ec-subnav-label', { hasText: 'Данные' })).toBeVisible()
    await expect(page.locator('.ec-subnav-item', { hasText: 'Расписание загрузки' })).toBeVisible()
    await expect(page.locator('.ec-subnav-item', { hasText: 'Загрузка каталога' })).toBeVisible()
    await expect(page.locator('.ec-subnav-item', { hasText: 'Наличие данных' })).toBeVisible()
    await expect(page.locator('.ec-subnav-label', { hasText: 'Финансы' })).toBeVisible()
    await expect(page.locator('.ec-subnav-item', { hasText: 'Себестоимость' })).toBeVisible()
    await expect(page.locator('.ec-subnav-item', { hasText: 'Расходы' })).toBeVisible()
    await expect(page.locator('.ec-subnav-item', { hasText: 'Налоги' })).toBeVisible()
    await expect(page.locator('.ec-subnav-label', { hasText: 'Интеграции' })).toBeVisible()
    await expect(page.locator('.ec-subnav-item', { hasText: 'Подключение МП' })).toBeVisible()
    await expect(page.locator('.ec-subnav-item', { hasText: 'Прокси' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Прокси для витрины WB' })).toHaveCount(0)
    await expect(page.getByRole('heading', { name: 'Себестоимость' })).toHaveCount(0)

    await page.goto('/app/project/1/cogs?ui=v2', { waitUntil: 'domcontentloaded' })
    await expect(page.locator('.ec-rail-item.is-active')).toHaveText(/Настр\./)
    await expect(page.locator('.ec-subnav-item.is-active')).toHaveText(/Себестоимость/)

    await page.goto('/app/project/1/additional-costs?ui=v2', { waitUntil: 'domcontentloaded' })
    await expect(page.locator('.ec-rail-item.is-active')).toHaveText(/Настр\./)
    await expect(page.locator('.ec-subnav-item.is-active')).toHaveText(/Расходы/)

    await page.goto('/app/project/1/settings/taxes?ui=v2', { waitUntil: 'domcontentloaded' })
    await expect(page.locator('.ec-rail-item.is-active')).toHaveText(/Настр\./)
    await expect(page.locator('.ec-subnav-item.is-active')).toHaveText(/Налоги/)

    await page.goto('/app/projects?ui=v2', { waitUntil: 'domcontentloaded' })
    await expect(page.locator('.ec-ui-v2')).toBeVisible()
    await expect(page.locator('.ec-rail')).toHaveCount(0)
    await expect(page.getByRole('heading', { name: 'Проекты' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Intro-Version' })).toBeVisible()
    await expect(page.getByText('Рабочие пространства')).toHaveCount(0)
    await expect(page.getByText('Инструменты платформы')).toHaveCount(0)
    await expect(page.getByText('Список проектов')).toHaveCount(0)
    await expect(page.getByText('Выручка 7д')).toHaveCount(0)
    await expect(page.getByText('Заказы 7д')).toHaveCount(0)
    await expect(page.getByText('Сигналов')).toHaveCount(0)
    await expect(page.getByText('Карточек')).toHaveCount(0)
  })

  test('renders project dashboard with current real capabilities only', async ({ page }) => {
    await page.goto('/app/project/1/dashboard?ui=v2', { waitUntil: 'domcontentloaded' })
    const dashboard = page.locator('[class*="dashboardPage"]')

    await expect(dashboard.getByRole('heading', { name: 'Intro-Version' })).toBeVisible()
    await expect(dashboard.getByText('Пульс проекта')).toBeVisible()
    await expect(dashboard.getByRole('heading', { name: 'Wildberries' })).toBeVisible()
    await expect(dashboard.getByText('Операционные счётчики по последним доступным снимкам')).toHaveCount(0)
    await expect(dashboard.getByText('Каталог WB')).toBeVisible()
    await expect(dashboard.getByText('790')).toBeVisible()
    await expect(dashboard.getByText('На витрине из 847 (93%)')).toBeVisible()
    await expect(dashboard.getByText('Остатки FBS / FBO')).toBeVisible()
    await expect(dashboard.getByText('Расхождения цен')).toHaveCount(0)

    await expect(dashboard.getByText('Требует внимания')).toHaveCount(0)
    await expect(dashboard.getByText('Сигналы')).toHaveCount(0)
    await expect(dashboard.getByText('В работе')).toHaveCount(0)
    await expect(dashboard.getByText('Гипотезы')).toHaveCount(0)
    await expect(dashboard.getByText('Цели')).toHaveCount(0)
    await expect(dashboard.getByText('Выручка')).toHaveCount(0)
    await expect(dashboard.getByText('Заказы')).toHaveCount(0)
    await expect(dashboard.getByText('Цены WB')).toHaveCount(0)
    await expect(dashboard.getByText('РРЦ XML')).toHaveCount(0)
    await expect(dashboard.getByText('Последний фин. отчёт WB')).toHaveCount(0)
  })
})
