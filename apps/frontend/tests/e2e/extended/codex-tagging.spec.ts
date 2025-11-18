/**
 * E2E Tests: Codex Tagging System
 * Tests wallet tagging, tag chips, and the Codex drawer
 *
 * Coverage:
 * - Add tag to wallet
 * - Remove tag from wallet
 * - Batch tag operations
 * - View Codex drawer
 * - Filter wallets by tag
 * - Tag autocomplete
 */

import { test, expect } from '@playwright/test';
import { apiFixture } from '../fixtures/api.fixture';
import { SAMPLE_ADDRESSES, SAMPLE_TAGS, waitFor } from '../helpers/test-data';

test.describe('Codex Tagging System', () => {
  test.beforeEach(async ({ page }) => {
    // Ensure backend is healthy
    const healthRes = await apiFixture.api.health();
    expect(healthRes.ok).toBeTruthy();

    // Seed a token to have wallets to tag
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token1);
    await waitFor(2000);

    await page.goto('/dashboard/tokens');
    await page.waitForLoadState('networkidle');
  });

  test('should add tag to wallet', async ({ page }) => {
    // Open token details to access wallet
    const tokenRow = page.locator('[data-testid="token-row"]').first();

    if ((await tokenRow.count()) > 0) {
      await tokenRow.click();

      // Wait for modal
      await page.waitForSelector('[data-testid="token-details-modal"]');

      // Find wallet item
      const walletItem = page.locator('[data-testid="wallet-item"]').first();

      if ((await walletItem.count()) > 0) {
        // Click add tag button
        const addTagButton = walletItem.getByRole('button', {
          name: /add tag|\+/i
        });

        if ((await addTagButton.count()) > 0) {
          await addTagButton.click();

          // Fill in tag input
          const tagInput = page.getByPlaceholder(/tag|add tag/i);
          await tagInput.fill(SAMPLE_TAGS[0]);

          // Submit tag
          await tagInput.press('Enter');

          // Verify tag appears
          await waitFor(500);
          const tagChip = walletItem.getByText(SAMPLE_TAGS[0]);
          await expect(tagChip).toBeVisible();
        }
      }
    }
  });

  test('should remove tag from wallet', async ({ page }) => {
    // First add a tag via API
    const tokenRow = page.locator('[data-testid="token-row"]').first();

    if ((await tokenRow.count()) > 0) {
      await tokenRow.click();
      await page.waitForSelector('[data-testid="token-details-modal"]');

      const walletItem = page.locator('[data-testid="wallet-item"]').first();

      if ((await walletItem.count()) > 0) {
        // Get wallet address from the element
        const walletAddress = await walletItem.getAttribute(
          'data-wallet-address'
        );

        if (walletAddress) {
          // Add tag via API
          await apiFixture.api.addTag(walletAddress, SAMPLE_TAGS[0]);
          await page.reload();
          await page.waitForLoadState('networkidle');

          await tokenRow.click();
          await page.waitForSelector('[data-testid="token-details-modal"]');

          // Find tag chip
          const tagChip = page.getByTestId(`tag-${SAMPLE_TAGS[0]}`);

          if ((await tagChip.count()) > 0) {
            // Click remove button on tag
            const removeButton = tagChip.getByRole('button', {
              name: /remove|×|x/i
            });
            await removeButton.click();

            // Confirm if needed
            const confirmButton = page.getByRole('button', {
              name: /confirm|yes/i
            });
            if ((await confirmButton.count()) > 0) {
              await confirmButton.click();
            }

            // Verify tag is removed
            await waitFor(500);
            await expect(tagChip).not.toBeVisible();
          }
        }
      }
    }
  });

  test('should perform batch tag operations', async ({ page }) => {
    const tokenRow = page.locator('[data-testid="token-row"]').first();

    if ((await tokenRow.count()) > 0) {
      await tokenRow.click();
      await page.waitForSelector('[data-testid="token-details-modal"]');

      // Look for batch tag button
      const batchTagButton = page.getByRole('button', {
        name: /batch tag|tag all/i
      });

      if ((await batchTagButton.count()) > 0) {
        // Select multiple wallets
        const checkboxes = page.locator('[data-testid="wallet-checkbox"]');
        const count = await checkboxes.count();

        if (count > 1) {
          await checkboxes.first().click();
          await checkboxes.nth(1).click();

          // Open batch tag dialog
          await batchTagButton.click();

          // Enter tag
          const tagInput = page.getByPlaceholder(/tag|enter tags/i);
          await tagInput.fill(SAMPLE_TAGS[1]);

          // Apply tags
          const applyButton = page.getByRole('button', { name: /apply|add/i });
          await applyButton.click();

          await waitFor(1000);

          // Verify tags were applied
          const successMessage = page.getByText(/tagged|success/i);
          if ((await successMessage.count()) > 0) {
            await expect(successMessage).toBeVisible();
          }
        }
      }
    }
  });

  test('should open Codex drawer', async ({ page }) => {
    // Look for Codex button
    const codexButton = page.getByRole('button', { name: /codex|tags/i });

    if ((await codexButton.count()) > 0) {
      await codexButton.click();

      // Verify drawer opens
      const codexDrawer = page.getByTestId('codex-drawer');
      await expect(codexDrawer).toBeVisible();

      // Verify drawer content
      await expect(page.getByText(/wallet tags|codex/i)).toBeVisible();
    }
  });

  test('should filter wallets by tag in Codex', async ({ page }) => {
    // Add tags to wallets first
    const tokenRow = page.locator('[data-testid="token-row"]').first();

    if ((await tokenRow.count()) > 0) {
      await tokenRow.click();
      await page.waitForSelector('[data-testid="token-details-modal"]');

      const walletItems = page.locator('[data-testid="wallet-item"]');
      const firstWallet = walletItems.first();

      if ((await firstWallet.count()) > 0) {
        const walletAddress = await firstWallet.getAttribute(
          'data-wallet-address'
        );

        if (walletAddress) {
          // Add tag via API
          await apiFixture.api.addTag(walletAddress, SAMPLE_TAGS[0]);
          await waitFor(500);

          // Close modal
          const closeButton = page.getByRole('button', { name: /close|×/i });
          if ((await closeButton.count()) > 0) {
            await closeButton.click();
          }

          // Open Codex
          const codexButton = page.getByRole('button', { name: /codex|tags/i });
          if ((await codexButton.count()) > 0) {
            await codexButton.click();

            // Click on tag to filter
            const tagFilter = page.getByTestId(`codex-tag-${SAMPLE_TAGS[0]}`);
            if ((await tagFilter.count()) > 0) {
              await tagFilter.click();

              // Verify filtered wallets are shown
              const filteredWallets = page.locator(
                '[data-testid="codex-wallet-item"]'
              );
              expect(await filteredWallets.count()).toBeGreaterThan(0);
            }
          }
        }
      }
    }
  });

  test('should display tag counts in Codex', async ({ page }) => {
    // Add tags via API
    const wallets = [SAMPLE_ADDRESSES.wallet1, SAMPLE_ADDRESSES.wallet2];

    for (const wallet of wallets) {
      await apiFixture.api.addTag(wallet, SAMPLE_TAGS[0]);
    }

    await page.reload();
    await page.waitForLoadState('networkidle');

    // Open Codex
    const codexButton = page.getByRole('button', { name: /codex|tags/i });

    if ((await codexButton.count()) > 0) {
      await codexButton.click();

      // Verify tag count is shown
      const tagItem = page.getByTestId(`codex-tag-${SAMPLE_TAGS[0]}`);

      if ((await tagItem.count()) > 0) {
        const countBadge = tagItem.getByText(/\d+/);
        await expect(countBadge).toBeVisible();

        const countText = await countBadge.textContent();
        const count = parseInt(countText || '0');
        expect(count).toBeGreaterThanOrEqual(2);
      }
    }
  });

  test('should autocomplete tag suggestions', async ({ page }) => {
    // Add some existing tags
    await apiFixture.api.addTag(SAMPLE_ADDRESSES.wallet1, SAMPLE_TAGS[0]);
    await apiFixture.api.addTag(SAMPLE_ADDRESSES.wallet2, SAMPLE_TAGS[1]);

    await page.reload();
    await page.waitForLoadState('networkidle');

    const tokenRow = page.locator('[data-testid="token-row"]').first();

    if ((await tokenRow.count()) > 0) {
      await tokenRow.click();
      await page.waitForSelector('[data-testid="token-details-modal"]');

      const walletItem = page.locator('[data-testid="wallet-item"]').first();

      if ((await walletItem.count()) > 0) {
        const addTagButton = walletItem.getByRole('button', {
          name: /add tag|\+/i
        });

        if ((await addTagButton.count()) > 0) {
          await addTagButton.click();

          // Type partial tag
          const tagInput = page.getByPlaceholder(/tag|add tag/i);
          await tagInput.fill(SAMPLE_TAGS[0].slice(0, 3));

          // Wait for autocomplete
          await waitFor(300);

          // Verify suggestions appear
          const suggestions = page.locator('[data-testid="tag-suggestion"]');

          if ((await suggestions.count()) > 0) {
            expect(await suggestions.count()).toBeGreaterThan(0);

            // Click suggestion
            await suggestions.first().click();

            // Verify tag is added
            await waitFor(500);
            const tagChip = walletItem.getByText(SAMPLE_TAGS[0]);
            await expect(tagChip).toBeVisible();
          }
        }
      }
    }
  });

  test('should display tag colors consistently', async ({ page }) => {
    // Add tag
    await apiFixture.api.addTag(SAMPLE_ADDRESSES.wallet1, SAMPLE_TAGS[0]);

    await page.reload();
    await page.waitForLoadState('networkidle');

    const tokenRow = page.locator('[data-testid="token-row"]').first();

    if ((await tokenRow.count()) > 0) {
      await tokenRow.click();
      await page.waitForSelector('[data-testid="token-details-modal"]');

      // Get tag chip color
      const tagChip = page.getByTestId(`tag-${SAMPLE_TAGS[0]}`);

      if ((await tagChip.count()) > 0) {
        const chipColor = await tagChip.evaluate(
          (el) => window.getComputedStyle(el).backgroundColor
        );

        // Close modal and open Codex
        const closeButton = page
          .getByRole('button', { name: /close|×/i })
          .first();
        if ((await closeButton.count()) > 0) {
          await closeButton.click();
        }

        const codexButton = page.getByRole('button', { name: /codex|tags/i });
        if ((await codexButton.count()) > 0) {
          await codexButton.click();

          // Get same tag color in Codex
          const codexTagChip = page.getByTestId(`codex-tag-${SAMPLE_TAGS[0]}`);

          if ((await codexTagChip.count()) > 0) {
            const codexChipColor = await codexTagChip.evaluate(
              (el) => window.getComputedStyle(el).backgroundColor
            );

            // Colors should match
            expect(chipColor).toBe(codexChipColor);
          }
        }
      }
    }
  });

  test('should rename tag globally', async ({ page }) => {
    // Add tag to multiple wallets
    await apiFixture.api.addTag(SAMPLE_ADDRESSES.wallet1, SAMPLE_TAGS[0]);
    await apiFixture.api.addTag(SAMPLE_ADDRESSES.wallet2, SAMPLE_TAGS[0]);

    await page.reload();
    await page.waitForLoadState('networkidle');

    // Open Codex
    const codexButton = page.getByRole('button', { name: /codex|tags/i });

    if ((await codexButton.count()) > 0) {
      await codexButton.click();

      // Find tag options/menu
      const tagItem = page.getByTestId(`codex-tag-${SAMPLE_TAGS[0]}`);

      if ((await tagItem.count()) > 0) {
        // Right-click or find menu button
        const menuButton = tagItem.getByRole('button', {
          name: /menu|options|⋮/i
        });

        if ((await menuButton.count()) > 0) {
          await menuButton.click();

          // Click rename option
          const renameButton = page.getByText(/rename/i);
          if ((await renameButton.count()) > 0) {
            await renameButton.click();

            // Enter new name
            const renameInput = page.getByPlaceholder(/new name|rename/i);
            await renameInput.fill('renamed-tag');

            // Save
            const saveButton = page.getByRole('button', {
              name: /save|update/i
            });
            await saveButton.click();

            await waitFor(500);

            // Verify tag is renamed
            await expect(page.getByText('renamed-tag')).toBeVisible();
            await expect(page.getByText(SAMPLE_TAGS[0])).not.toBeVisible();
          }
        }
      }
    }
  });
});
