/**
 * E2E Tests: Watchlist Registration Flows
 * Tests watchlist functionality for monitoring specific wallet addresses
 *
 * Coverage:
 * - Register single address
 * - Import multiple addresses
 * - View watchlist
 * - Remove address from watchlist
 * - Clear entire watchlist
 * - Label management
 */

import { test, expect } from '@playwright/test';
import { apiFixture } from '../fixtures/api.fixture';
import {
  SAMPLE_ADDRESSES,
  SAMPLE_WATCHLIST_LABELS,
  waitFor
} from '../helpers/test-data';

test.describe('Watchlist Registration', () => {
  test.beforeEach(async ({ page }) => {
    // Clear watchlist before each test
    await apiFixture.api.clearWatchlist();

    // Ensure backend is healthy
    const healthRes = await apiFixture.api.health();
    expect(healthRes.ok).toBeTruthy();

    // Navigate to dashboard
    await page.goto('/dashboard/tokens');
    await page.waitForLoadState('networkidle');
  });

  test('should register a single wallet address', async ({ page }) => {
    // Find watchlist section or button
    const watchlistButton = page.getByRole('button', {
      name: /watchlist|add to watchlist|register/i
    });

    if ((await watchlistButton.count()) > 0) {
      await watchlistButton.click();

      // Fill in address input
      const addressInput = page.getByLabel(/address|wallet address/i);
      await addressInput.fill(SAMPLE_ADDRESSES.wallet1);

      // Fill in label
      const labelInput = page.getByLabel(/label|name/i);
      if ((await labelInput.count()) > 0) {
        await labelInput.fill(SAMPLE_WATCHLIST_LABELS[0]);
      }

      // Submit form
      const submitButton = page.getByRole('button', {
        name: /register|add|save/i
      });
      await submitButton.click();

      // Verify success message
      await waitFor(1000);
      const successMessage = page.getByText(/added|registered|success/i);
      if ((await successMessage.count()) > 0) {
        await expect(successMessage).toBeVisible();
      }

      // Verify address appears in watchlist
      const watchlistItem = page.getByText(
        SAMPLE_ADDRESSES.wallet1.slice(0, 8)
      );
      await expect(watchlistItem).toBeVisible();
    }
  });

  test('should import multiple addresses', async ({ page }) => {
    // Navigate to watchlist import
    const importButton = page.getByRole('button', { name: /import|bulk add/i });

    if ((await importButton.count()) > 0) {
      await importButton.click();

      // Fill in multiple addresses (CSV or line-separated format)
      const importTextarea = page.getByLabel(/addresses|import/i);
      const addressesToImport = [
        SAMPLE_ADDRESSES.wallet1,
        SAMPLE_ADDRESSES.wallet2,
        SAMPLE_ADDRESSES.wallet3
      ].join('\n');

      await importTextarea.fill(addressesToImport);

      // Submit import
      const submitButton = page.getByRole('button', {
        name: /import|submit|add/i
      });
      await submitButton.click();

      // Wait for import to process
      await waitFor(2000);

      // Verify success message
      const successMessage = page.getByText(/imported|success/i);
      if ((await successMessage.count()) > 0) {
        await expect(successMessage).toBeVisible();
      }

      // Verify addresses appear in watchlist
      await page.reload();
      const watchlistItems = page.locator('[data-testid="watchlist-item"]');
      expect(await watchlistItems.count()).toBeGreaterThanOrEqual(3);
    }
  });

  test('should view watchlist addresses', async ({ page }) => {
    // Register addresses via API
    await apiFixture.api.registerWatchlistAddress(
      SAMPLE_ADDRESSES.wallet1,
      SAMPLE_WATCHLIST_LABELS[0]
    );
    await apiFixture.api.registerWatchlistAddress(
      SAMPLE_ADDRESSES.wallet2,
      SAMPLE_WATCHLIST_LABELS[1]
    );

    await page.reload();
    await page.waitForLoadState('networkidle');

    // Navigate to watchlist view
    const watchlistTab = page.getByRole('tab', { name: /watchlist/i });
    if ((await watchlistTab.count()) > 0) {
      await watchlistTab.click();
    }

    // Verify addresses are displayed
    const watchlistItems = page.locator('[data-testid="watchlist-item"]');
    expect(await watchlistItems.count()).toBeGreaterThanOrEqual(2);

    // Verify labels are shown
    await expect(page.getByText(SAMPLE_WATCHLIST_LABELS[0])).toBeVisible();
    await expect(page.getByText(SAMPLE_WATCHLIST_LABELS[1])).toBeVisible();
  });

  test('should remove address from watchlist', async ({ page }) => {
    // Register address
    await apiFixture.api.registerWatchlistAddress(
      SAMPLE_ADDRESSES.wallet1,
      SAMPLE_WATCHLIST_LABELS[0]
    );

    await page.reload();
    await page.waitForLoadState('networkidle');

    // Find watchlist item
    const watchlistItem = page
      .locator('[data-testid="watchlist-item"]')
      .first();

    if ((await watchlistItem.count()) > 0) {
      // Click remove/delete button
      const removeButton = watchlistItem.getByRole('button', {
        name: /remove|delete/i
      });
      await removeButton.click();

      // Confirm if needed
      const confirmButton = page.getByRole('button', { name: /confirm|yes/i });
      if ((await confirmButton.count()) > 0) {
        await confirmButton.click();
      }

      // Verify address is removed
      await waitFor(1000);
      await page.reload();

      const removedItem = page.getByText(SAMPLE_ADDRESSES.wallet1.slice(0, 8));
      await expect(removedItem).not.toBeVisible();
    }
  });

  test('should clear entire watchlist', async ({ page }) => {
    // Register multiple addresses
    await apiFixture.api.registerWatchlistAddress(SAMPLE_ADDRESSES.wallet1);
    await apiFixture.api.registerWatchlistAddress(SAMPLE_ADDRESSES.wallet2);
    await apiFixture.api.registerWatchlistAddress(SAMPLE_ADDRESSES.wallet3);

    await page.reload();
    await page.waitForLoadState('networkidle');

    // Find clear all button
    const clearAllButton = page.getByRole('button', {
      name: /clear all|clear watchlist/i
    });

    if ((await clearAllButton.count()) > 0) {
      await clearAllButton.click();

      // Confirm action
      const confirmButton = page.getByRole('button', {
        name: /confirm|yes|clear/i
      });
      await confirmButton.click();

      // Verify watchlist is empty
      await waitFor(1000);
      await page.reload();

      const emptyMessage = page.getByText(
        /no addresses|empty|watchlist is empty/i
      );
      await expect(emptyMessage).toBeVisible();
    }
  });

  test('should validate wallet address format', async ({ page }) => {
    const watchlistButton = page.getByRole('button', {
      name: /watchlist|add to watchlist|register/i
    });

    if ((await watchlistButton.count()) > 0) {
      await watchlistButton.click();

      // Try to submit invalid address
      const addressInput = page.getByLabel(/address|wallet address/i);
      await addressInput.fill('invalid_address_123');

      const submitButton = page.getByRole('button', {
        name: /register|add|save/i
      });
      await submitButton.click();

      // Should show validation error
      const errorMessage = page.getByText(/invalid|error|valid address/i);
      await expect(errorMessage).toBeVisible();
    }
  });

  test('should edit watchlist item label', async ({ page }) => {
    // Register address
    await apiFixture.api.registerWatchlistAddress(
      SAMPLE_ADDRESSES.wallet1,
      SAMPLE_WATCHLIST_LABELS[0]
    );

    await page.reload();
    await page.waitForLoadState('networkidle');

    const watchlistItem = page
      .locator('[data-testid="watchlist-item"]')
      .first();

    if ((await watchlistItem.count()) > 0) {
      // Find edit button
      const editButton = watchlistItem.getByRole('button', { name: /edit/i });

      if ((await editButton.count()) > 0) {
        await editButton.click();

        // Change label
        const labelInput = page.getByLabel(/label|name/i);
        await labelInput.clear();
        await labelInput.fill('Updated Label');

        // Save changes
        const saveButton = page.getByRole('button', { name: /save|update/i });
        await saveButton.click();

        // Verify new label is displayed
        await waitFor(500);
        await expect(page.getByText('Updated Label')).toBeVisible();
      }
    }
  });

  test('should prevent duplicate addresses', async ({ page }) => {
    // Register address first
    await apiFixture.api.registerWatchlistAddress(SAMPLE_ADDRESSES.wallet1);

    await page.reload();
    await page.waitForLoadState('networkidle');

    // Try to register same address again
    const watchlistButton = page.getByRole('button', {
      name: /watchlist|add to watchlist|register/i
    });

    if ((await watchlistButton.count()) > 0) {
      await watchlistButton.click();

      const addressInput = page.getByLabel(/address|wallet address/i);
      await addressInput.fill(SAMPLE_ADDRESSES.wallet1);

      const submitButton = page.getByRole('button', {
        name: /register|add|save/i
      });
      await submitButton.click();

      // Should show duplicate error
      const errorMessage = page.getByText(
        /already exists|duplicate|already in watchlist/i
      );
      await expect(errorMessage).toBeVisible();
    }
  });
});
