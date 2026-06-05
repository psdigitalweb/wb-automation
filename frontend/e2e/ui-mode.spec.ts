import { expect, test } from '@playwright/test'

const projects = [
  {
    id: 1,
    name: 'Intro-Version',
    description: null,
    created_by: 1,
    created_at: '2026-01-27T00:00:00Z',
    updated_at: '2026-01-27T00:00:00Z',
    role: 'owner',
  },
]

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/projects', (route) => route.fulfill({ json: projects }))
  await page.route('**/api/v1/projects/1', (route) => route.fulfill({ json: projects[0] }))
  await page.addInitScript(() => {
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

test.describe('UI mode feature flag', () => {
  test('enables UI v2 from query string and persists it', async ({ page }) => {
    await page.goto('/app/projects?ui=v2')
    await expect(page.locator('.ec-ui-v2')).toBeVisible()
    await expect(page.locator('.ec-rail')).toHaveCount(0)
    await expect(page.locator('.topbar')).toHaveCount(0)
    await expect(page).toHaveURL(/ui=v2/)
    await expect.poll(() => page.evaluate(() => localStorage.getItem('ecomcore.ui'))).toBe('v2')

    await page.goto('/app/projects')
    await expect(page.locator('.ec-ui-v2')).toBeVisible()
  })

  test('returns to UI v1 from query string and persists it', async ({ page }) => {
    await page.goto('/app/projects?ui=v1', { waitUntil: 'domcontentloaded' })
    await expect(page.locator('.topbar')).toBeVisible()
    await expect(page.locator('.ec-ui-v2')).toHaveCount(0)
    await expect.poll(() => page.evaluate(() => localStorage.getItem('ecomcore.ui'))).toBe('v1')
  })
})
