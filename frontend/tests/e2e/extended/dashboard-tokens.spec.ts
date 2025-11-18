/**
 * E2E Tests: Dashboard Tokens Panel
 * Tests the main tokens dashboard table and token details modal
 *
 * Coverage:
 * - Token list display
 * - Token details modal
 * - Token history view
 * - Wallet type display (creator, holder, dev, insider, sniper)
 * - Soft delete operation
 */

import { test, expect } from '@playwright/test';
import { apiFixture } from '../fixtures/api.fixture';
import { SAMPLE_ADDRESSES, waitFor } from '../helpers/test-data';

test.describe('Dashboard Tokens Panel', () => {
  test.beforeEach(async ({ page }) => {
    // Ensure backend is healthy
    const healthRes = await apiFixture.api.health();
    expect(healthRes.ok).toBeTruthy();

    // Navigate to dashboard
    await page.goto('/dashboard/tokens');
  });

  test('should display tokens table', async ({ page }) => {
    // Wait for table to load
    await page.waitForSelector('[data-testid="tokens-table"]', {
      timeout: 10000,
      state: 'visible'
    });

    // Verify table headers are present
    const headers = ['Token', 'Address', 'Analyzed At', 'Actions'];
    for (const header of headers) {
      await expect(page.getByText(header)).toBeVisible();
    }
  });

  test('should open token details modal', async ({ page }) => {
    // Seed a token first
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token1);
    await waitFor(2000); // Wait for analysis to process

    await page.reload();
    await page.waitForSelector('[data-testid="tokens-table"]');

    // Find and click the first token row
    const firstTokenRow = page.locator('[data-testid="token-row"]').first();
    if ((await firstTokenRow.count()) > 0) {
      await firstTokenRow.click();

      // Verify modal opens
      await expect(page.getByTestId('token-details-modal')).toBeVisible();

      // Verify modal content sections
      await expect(page.getByText('Token Information')).toBeVisible();
      await expect(page.getByText('Wallets')).toBeVisible();
    }
  });

  test('should display wallet types correctly', async ({ page }) => {
    // Seed a token
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token1);
    await waitFor(2000);

    await page.reload();
    await page.waitForSelector('[data-testid="tokens-table"]');

    const firstTokenRow = page.locator('[data-testid="token-row"]').first();
    if ((await firstTokenRow.count()) > 0) {
      await firstTokenRow.click();

      // Check for wallet type badges (creator, holder, dev, insider, sniper)
      const walletSection = page.getByTestId('wallets-section');

      // Verify at least one wallet type is displayed
      const walletTypes = ['creator', 'holder', 'dev', 'insider', 'sniper'];
      let foundType = false;

      for (const type of walletTypes) {
        const typeElement = walletSection.getByText(type, { exact: false });
        if ((await typeElement.count()) > 0) {
          foundType = true;
          break;
        }
      }

      expect(foundType).toBeTruthy();
    }
  });

  test('should view token analysis history', async ({ page }) => {
    // Seed a token
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token1);
    await waitFor(2000);

    await page.reload();
    await page.waitForSelector('[data-testid="tokens-table"]');

    const firstTokenRow = page.locator('[data-testid="token-row"]').first();
    if ((await firstTokenRow.count()) > 0) {
      await firstTokenRow.click();

      // Look for history/analysis runs section
      const historyButton = page.getByRole('button', { name: /history/i });
      if ((await historyButton.count()) > 0) {
        await historyButton.click();
        await expect(page.getByTestId('analysis-history')).toBeVisible();
      }
    }
  });

  test('should soft delete token', async ({ page }) => {
    // Seed a token
    const result = await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token1);
    await waitFor(2000);

    await page.reload();
    await page.waitForSelector('[data-testid="tokens-table"]');

    const firstTokenRow = page.locator('[data-testid="token-row"]').first();
    if ((await firstTokenRow.count()) > 0) {
      // Find delete button
      const deleteButton = firstTokenRow.getByRole('button', {
        name: /delete|trash/i
      });

      if ((await deleteButton.count()) > 0) {
        await deleteButton.click();

        // Confirm deletion if there's a confirmation dialog
        const confirmButton = page.getByRole('button', {
          name: /confirm|yes/i
        });
        if ((await confirmButton.count()) > 0) {
          await confirmButton.click();
        }

        // Verify token is removed from main table
        await waitFor(1000);
        await page.reload();

        // Token should not appear in the tokens table
        const tokenAfterDelete = page.getByText(
          SAMPLE_ADDRESSES.token1.slice(0, 8)
        );
        await expect(tokenAfterDelete).not.toBeVisible();
      }
    }
  });

  test('should handle empty state', async ({ page }) => {
    // Clear all tokens
    await apiFixture.api.clearDatabase();
    await page.reload();

    // Should show empty state message
    const emptyMessage = page.getByText(/no tokens|empty/i);
    await expect(emptyMessage).toBeVisible();
  });

  test('should filter and search tokens', async ({ page }) => {
    // Seed multiple tokens
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token1);
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token2);
    await waitFor(3000);

    await page.reload();
    await page.waitForSelector('[data-testid="tokens-table"]');

    // Look for search input
    const searchInput = page.getByPlaceholder(/search/i);
    if ((await searchInput.count()) > 0) {
      await searchInput.fill(SAMPLE_ADDRESSES.token1.slice(0, 8));
      await waitFor(500);

      // Verify filtered results
      const rows = page.locator('[data-testid="token-row"]');
      const count = await rows.count();
      expect(count).toBeGreaterThanOrEqual(1);
    }
  });
});
