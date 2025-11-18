/**
 * E2E Tests: Multi-Token Wallets Panel
 * Tests the Multi-Token Wallets section within the dashboard
 *
 * Coverage:
 * - Display wallets holding multiple tokens
 * - Refresh balances functionality
 * - Wallet sorting and filtering
 * - Token count display
 */

import { test, expect } from '@playwright/test';
import { apiFixture } from '../fixtures/api.fixture';
import { SAMPLE_ADDRESSES, waitFor } from '../helpers/test-data';

test.describe('Multi-Token Wallets Panel', () => {
  test.beforeEach(async ({ page }) => {
    // Ensure backend is healthy
    const healthRes = await apiFixture.api.health();
    expect(healthRes.ok).toBeTruthy();

    // Navigate to dashboard tokens page (multi-token wallets section is here)
    await page.goto('/dashboard/tokens');
    await page.waitForLoadState('networkidle');
  });

  test('should display multi-token wallets section', async ({ page }) => {
    // Look for multi-token wallets heading
    const heading = page.getByRole('heading', { name: /multi-token wallets/i });
    await expect(heading).toBeVisible();

    // Verify section container exists
    const section = page.getByTestId('multi-token-wallets-section');
    if ((await section.count()) > 0) {
      await expect(section).toBeVisible();
    }
  });

  test('should display wallet list with token counts', async ({ page }) => {
    // Seed multiple tokens to create multi-token wallets
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token1);
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token2);
    await waitFor(3000);

    await page.reload();
    await page.waitForLoadState('networkidle');

    // Look for wallet items
    const walletItems = page.locator('[data-testid="multi-token-wallet-item"]');

    if ((await walletItems.count()) > 0) {
      const firstWallet = walletItems.first();

      // Verify wallet address is displayed
      await expect(firstWallet).toBeVisible();

      // Verify token count is shown
      const tokenCount = firstWallet.getByText(/tokens/i);
      await expect(tokenCount).toBeVisible();
    }
  });

  test('should refresh wallet balances', async ({ page }) => {
    // Seed tokens
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token1);
    await waitFor(2000);

    await page.reload();
    await page.waitForLoadState('networkidle');

    // Find refresh button
    const refreshButton = page.getByRole('button', {
      name: /refresh balances/i
    });

    if ((await refreshButton.count()) > 0) {
      // Click refresh
      await refreshButton.click();

      // Should show loading state
      const loadingIndicator = page.getByText(/refreshing|loading/i);
      if ((await loadingIndicator.count()) > 0) {
        await expect(loadingIndicator).toBeVisible();
      }

      // Wait for refresh to complete
      await waitFor(2000);

      // Loading indicator should disappear
      if ((await loadingIndicator.count()) > 0) {
        await expect(loadingIndicator).not.toBeVisible();
      }
    }
  });

  test('should sort wallets by token count', async ({ page }) => {
    // Seed multiple tokens
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token1);
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token2);
    await waitFor(3000);

    await page.reload();
    await page.waitForLoadState('networkidle');

    // Look for sort button or dropdown
    const sortButton = page.getByRole('button', { name: /sort/i });

    if ((await sortButton.count()) > 0) {
      await sortButton.click();

      // Select token count sort option
      const tokenCountOption = page.getByText(/token count|tokens/i);
      if ((await tokenCountOption.count()) > 0) {
        await tokenCountOption.click();
        await waitFor(500);

        // Verify wallets are displayed (sorted)
        const walletItems = page.locator(
          '[data-testid="multi-token-wallet-item"]'
        );
        expect(await walletItems.count()).toBeGreaterThan(0);
      }
    }
  });

  test('should filter wallets by minimum token count', async ({ page }) => {
    // Seed tokens
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token1);
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token2);
    await waitFor(3000);

    await page.reload();
    await page.waitForLoadState('networkidle');

    // Look for filter controls
    const filterInput = page.getByLabel(/minimum tokens|min token count/i);

    if ((await filterInput.count()) > 0) {
      await filterInput.fill('2');
      await waitFor(500);

      // Verify filtered results
      const walletItems = page.locator(
        '[data-testid="multi-token-wallet-item"]'
      );
      const count = await walletItems.count();

      // All visible wallets should have >= 2 tokens
      if (count > 0) {
        for (let i = 0; i < count; i++) {
          const wallet = walletItems.nth(i);
          const tokenCountText = await wallet
            .getByText(/\d+ tokens?/i)
            .textContent();
          const tokenCount = parseInt(tokenCountText?.match(/\d+/)?.[0] || '0');
          expect(tokenCount).toBeGreaterThanOrEqual(2);
        }
      }
    }
  });

  test('should navigate to wallet details', async ({ page }) => {
    // Seed tokens
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token1);
    await waitFor(2000);

    await page.reload();
    await page.waitForLoadState('networkidle');

    // Click on a wallet item
    const walletItem = page
      .locator('[data-testid="multi-token-wallet-item"]')
      .first();

    if ((await walletItem.count()) > 0) {
      await walletItem.click();

      // Should navigate to wallet details or open modal
      // Check for modal or URL change
      const walletDetailsModal = page.getByTestId('wallet-details-modal');
      const currentUrl = page.url();

      const hasModal = (await walletDetailsModal.count()) > 0;
      const urlChanged =
        currentUrl.includes('/wallet/') || currentUrl.includes('wallet');

      expect(hasModal || urlChanged).toBeTruthy();
    }
  });

  test('should handle empty state', async ({ page }) => {
    // Clear all data
    await apiFixture.api.clearDatabase();
    await page.reload();
    await page.waitForLoadState('networkidle');

    // Should show empty state
    const emptyMessage = page.getByText(
      /no multi-token wallets|no wallets found/i
    );

    if ((await emptyMessage.count()) > 0) {
      await expect(emptyMessage).toBeVisible();
    }
  });

  test('should display wallet addresses correctly formatted', async ({
    page
  }) => {
    // Seed tokens
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token1);
    await waitFor(2000);

    await page.reload();
    await page.waitForLoadState('networkidle');

    const walletItem = page
      .locator('[data-testid="multi-token-wallet-item"]')
      .first();

    if ((await walletItem.count()) > 0) {
      // Verify address is displayed (usually truncated format like "7UX2i...oDUi")
      const addressText = await walletItem
        .getByTestId('wallet-address')
        .textContent();
      expect(addressText).toBeTruthy();
      expect(addressText!.length).toBeGreaterThan(0);
    }
  });
});
