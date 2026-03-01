import { test, expect } from '@playwright/test'

test.describe('Node Management', () => {
  test('Add Node button is visible when Mesh Nodes panel is open', async ({ page }) => {
    await page.goto('/')
    // Open Mesh Nodes panel
    await page.getByText('Mesh Nodes').click()
    // Button should appear
    await expect(page.getByText('Add Node')).toBeVisible()
  })
})
