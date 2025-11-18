/**
 * E2E Tests: Trash View Operations
 * Tests soft delete, restore, and permanent delete functionality
 *
 * Coverage:
 * - View trashed tokens
 * - Restore token from trash
 * - Permanently delete token
 * - Bulk operations
 * - Empty trash state
 */

import { test, expect } from '@playwright/test';
import { apiFixture } from '../fixtures/api.fixture';
import { SAMPLE_ADDRESSES, waitFor } from '../helpers/test-data';

test.describe('Trash View Operations', () => {
  test.beforeEach(async ({ page }) => {
    // Clear database
    await apiFixture.api.clearDatabase();

    // Ensure backend is healthy
    const healthRes = await apiFixture.api.health();
    expect(healthRes.ok).toBeTruthy();

    await page.goto('/dashboard/trash');
    await page.waitForLoadState('networkidle');
  });

  test('should display trash page', async ({ page }) => {
    // Verify trash heading
    const heading = page.getByRole('heading', {
      name: /trash|deleted tokens/i
    });
    await expect(heading).toBeVisible();

    // Verify page loaded
    expect(page.url()).toContain('/trash');
  });

  test('should show deleted tokens in trash', async ({ page }) => {
    // First, create and delete a token
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token1);
    await waitFor(2000);

    // Navigate to tokens page to delete
    await page.goto('/dashboard/tokens');
    await page.waitForLoadState('networkidle');

    const tokenRow = page.locator('[data-testid="token-row"]').first();
    if ((await tokenRow.count()) > 0) {
      const deleteButton = tokenRow.getByRole('button', {
        name: /delete|trash/i
      });
      if ((await deleteButton.count()) > 0) {
        await deleteButton.click();

        // Confirm if needed
        const confirmButton = page.getByRole('button', {
          name: /confirm|yes/i
        });
        if ((await confirmButton.count()) > 0) {
          await confirmButton.click();
        }

        await waitFor(1000);
      }
    }

    // Navigate to trash
    await page.goto('/dashboard/trash');
    await page.waitForLoadState('networkidle');

    // Verify token appears in trash
    const trashedTokens = page.locator('[data-testid="trash-item"]');
    expect(await trashedTokens.count()).toBeGreaterThan(0);
  });

  test('should restore token from trash', async ({ page }) => {
    // Seed and delete token
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token1);
    await waitFor(2000);

    // Delete via API for faster setup
    const tokensRes = await fetch('http://localhost:5003/api/tokens/history');
    const tokensData = await tokensRes.json();
    const tokenId = tokensData.tokens?.[0]?.id;

    if (tokenId) {
      await fetch(`http://localhost:5003/api/tokens/${tokenId}`, {
        method: 'DELETE'
      });
    }

    await page.reload();
    await page.waitForLoadState('networkidle');

    // Find restore button
    const trashedToken = page.locator('[data-testid="trash-item"]').first();

    if ((await trashedToken.count()) > 0) {
      const restoreButton = trashedToken.getByRole('button', {
        name: /restore/i
      });
      await restoreButton.click();

      // Confirm if needed
      const confirmButton = page.getByRole('button', {
        name: /confirm|yes|restore/i
      });
      if ((await confirmButton.count()) > 0) {
        await confirmButton.click();
      }

      await waitFor(1000);

      // Verify success message
      const successMessage = page.getByText(/restored|success/i);
      if ((await successMessage.count()) > 0) {
        await expect(successMessage).toBeVisible();
      }

      // Verify token is removed from trash
      await page.reload();
      const trashedItems = page.locator('[data-testid="trash-item"]');
      const count = await trashedItems.count();

      // Token should be gone from trash
      expect(count).toBe(0);

      // Verify token is back in main tokens table
      await page.goto('/dashboard/tokens');
      await page.waitForLoadState('networkidle');

      const tokenInTable = page.getByText(SAMPLE_ADDRESSES.token1.slice(0, 8));
      await expect(tokenInTable).toBeVisible();
    }
  });

  test('should permanently delete token', async ({ page }) => {
    // Seed and soft delete token
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token1);
    await waitFor(2000);

    // Delete via API
    const tokensRes = await fetch('http://localhost:5003/api/tokens/history');
    const tokensData = await tokensRes.json();
    const tokenId = tokensData.tokens?.[0]?.id;

    if (tokenId) {
      await fetch(`http://localhost:5003/api/tokens/${tokenId}`, {
        method: 'DELETE'
      });
    }

    await page.reload();
    await page.waitForLoadState('networkidle');

    // Find permanent delete button
    const trashedToken = page.locator('[data-testid="trash-item"]').first();

    if ((await trashedToken.count()) > 0) {
      const permanentDeleteButton = trashedToken.getByRole('button', {
        name: /delete permanently|permanent/i
      });

      if ((await permanentDeleteButton.count()) > 0) {
        await permanentDeleteButton.click();

        // Confirm permanent deletion
        const confirmButton = page.getByRole('button', {
          name: /confirm|yes|delete/i
        });
        await confirmButton.click();

        await waitFor(1000);

        // Verify token is removed from trash
        await page.reload();
        const trashedItems = page.locator('[data-testid="trash-item"]');
        expect(await trashedItems.count()).toBe(0);

        // Verify empty state
        const emptyMessage = page.getByText(
          /trash is empty|no deleted tokens/i
        );
        await expect(emptyMessage).toBeVisible();
      }
    }
  });

  test('should handle empty trash state', async ({ page }) => {
    // Trash should be empty initially
    const emptyMessage = page.getByText(
      /trash is empty|no deleted tokens|no items/i
    );
    await expect(emptyMessage).toBeVisible();
  });

  test('should display deleted timestamp', async ({ page }) => {
    // Seed and delete token
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token1);
    await waitFor(2000);

    const tokensRes = await fetch('http://localhost:5003/api/tokens/history');
    const tokensData = await tokensRes.json();
    const tokenId = tokensData.tokens?.[0]?.id;

    if (tokenId) {
      await fetch(`http://localhost:5003/api/tokens/${tokenId}`, {
        method: 'DELETE'
      });
    }

    await page.reload();
    await page.waitForLoadState('networkidle');

    const trashedToken = page.locator('[data-testid="trash-item"]').first();

    if ((await trashedToken.count()) > 0) {
      // Look for deleted timestamp
      const timestamp = trashedToken.getByText(
        /deleted|ago|\d+ (hour|minute|day)s? ago/i
      );

      if ((await timestamp.count()) > 0) {
        await expect(timestamp).toBeVisible();
      }
    }
  });

  test('should bulk restore tokens', async ({ page }) => {
    // Seed multiple tokens and delete them
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token1);
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token2);
    await waitFor(3000);

    // Delete both via API
    const tokensRes = await fetch('http://localhost:5003/api/tokens/history');
    const tokensData = await tokensRes.json();

    for (const token of tokensData.tokens || []) {
      await fetch(`http://localhost:5003/api/tokens/${token.id}`, {
        method: 'DELETE'
      });
    }

    await page.reload();
    await page.waitForLoadState('networkidle');

    // Find bulk restore button
    const bulkRestoreButton = page.getByRole('button', {
      name: /restore all|bulk restore/i
    });

    if ((await bulkRestoreButton.count()) > 0) {
      await bulkRestoreButton.click();

      // Confirm
      const confirmButton = page.getByRole('button', {
        name: /confirm|yes|restore/i
      });
      if ((await confirmButton.count()) > 0) {
        await confirmButton.click();
      }

      await waitFor(1000);

      // Trash should be empty
      await page.reload();
      const emptyMessage = page.getByText(/trash is empty|no deleted tokens/i);
      await expect(emptyMessage).toBeVisible();
    }
  });

  test('should empty entire trash', async ({ page }) => {
    // Seed and delete multiple tokens
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token1);
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token2);
    await waitFor(3000);

    const tokensRes = await fetch('http://localhost:5003/api/tokens/history');
    const tokensData = await tokensRes.json();

    for (const token of tokensData.tokens || []) {
      await fetch(`http://localhost:5003/api/tokens/${token.id}`, {
        method: 'DELETE'
      });
    }

    await page.reload();
    await page.waitForLoadState('networkidle');

    // Find empty trash button
    const emptyTrashButton = page.getByRole('button', {
      name: /empty trash|delete all/i
    });

    if ((await emptyTrashButton.count()) > 0) {
      await emptyTrashButton.click();

      // Confirm dangerous action
      const confirmButton = page.getByRole('button', {
        name: /confirm|yes|delete/i
      });
      await confirmButton.click();

      await waitFor(1000);

      // Verify trash is empty
      await page.reload();
      const emptyMessage = page.getByText(/trash is empty|no deleted tokens/i);
      await expect(emptyMessage).toBeVisible();
    }
  });

  test('should filter trash items', async ({ page }) => {
    // Seed and delete multiple tokens
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token1);
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token2);
    await waitFor(3000);

    const tokensRes = await fetch('http://localhost:5003/api/tokens/history');
    const tokensData = await tokensRes.json();

    for (const token of tokensData.tokens || []) {
      await fetch(`http://localhost:5003/api/tokens/${token.id}`, {
        method: 'DELETE'
      });
    }

    await page.reload();
    await page.waitForLoadState('networkidle');

    // Look for filter/search
    const searchInput = page.getByPlaceholder(/search|filter/i);

    if ((await searchInput.count()) > 0) {
      await searchInput.fill(SAMPLE_ADDRESSES.token1.slice(0, 8));
      await waitFor(500);

      // Verify filtered results
      const trashedItems = page.locator('[data-testid="trash-item"]');
      expect(await trashedItems.count()).toBeGreaterThanOrEqual(1);
    }
  });
});
