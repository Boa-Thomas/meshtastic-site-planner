import { test, expect } from '@playwright/test'

test.describe('Coverage Simulation', () => {
  test('page loads and shows the map', async ({ page }) => {
    await page.goto('/')
    // The map div should be visible
    await expect(page.locator('#map')).toBeVisible()
    // Navbar should be present
    await expect(page.locator('.navbar-brand')).toContainText('Meshtastic Site Planner')
  })

  test('sidebar has all panels', async ({ page }) => {
    await page.goto('/')
    // Check for panel headers
    await expect(page.getByText('Site / Transmitter')).toBeVisible()
    await expect(page.getByText('Receiver')).toBeVisible()
    await expect(page.getByText('Environment')).toBeVisible()
    await expect(page.getByText('Simulation Options')).toBeVisible()
    await expect(page.getByText('Display')).toBeVisible()
    await expect(page.getByText('Mesh Nodes')).toBeVisible()
    await expect(page.getByText('Network Simulation (DES)')).toBeVisible()
  })

  test('Run Simulation button is present and enabled', async ({ page }) => {
    await page.goto('/')
    const btn = page.locator('#runSimulation')
    await expect(btn).toBeVisible()
    await expect(btn).toBeEnabled()
  })
})
