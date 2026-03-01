import { test, expect } from '@playwright/test'

test.describe('DES Simulation', () => {
  test('DES panel shows Initialize button when nodes exist', async ({ page }) => {
    await page.goto('/')
    // Open DES panel
    await page.getByText('Network Simulation (DES)').click()
    // Should show the initialize button (possibly disabled since no nodes yet)
    await expect(page.getByText('Initialize DES')).toBeVisible()
  })
})
