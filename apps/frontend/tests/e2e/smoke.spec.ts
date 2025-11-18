/**
 * Smoke Tests - Minimal validation for CI
 * Only validates that critical pages load successfully
 */

import { test, expect } from '@playwright/test';

test.describe('Smoke Tests', () => {
  test('dashboard tokens page loads', async ({ page }) => {
    await page.goto('/dashboard/tokens');
    await expect(page.locator('h1')).toContainText('Analyzed Tokens');
  });

  test('trash page loads', async ({ page }) => {
    await page.goto('/dashboard/trash');
    await expect(page.locator('h1')).toContainText('Trash');
  });

  test('health endpoint responds', async ({ request }) => {
    const response = await request.get('http://localhost:5003/health');
    expect(response.status()).toBe(200);
  });
});
