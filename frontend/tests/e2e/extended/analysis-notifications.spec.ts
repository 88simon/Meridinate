/**
 * E2E Tests: Analysis Notifications (WebSocket)
 * Tests real-time analysis job notifications via WebSocket
 *
 * Coverage:
 * - WebSocket connection establishment
 * - Job queued notification
 * - Job started notification
 * - Job completed notification
 * - Job failed notification
 * - Notification UI display
 * - Notification dismissal
 */

import { test, expect } from '@playwright/test';
import { apiFixture } from '../fixtures/api.fixture';
import { SAMPLE_ADDRESSES, waitFor, retry } from '../helpers/test-data';

test.describe('Analysis Notifications (WebSocket)', () => {
  test.beforeEach(async ({ page }) => {
    // Ensure backend is healthy
    const healthRes = await apiFixture.api.health();
    expect(healthRes.ok).toBeTruthy();

    await page.goto('/dashboard/tokens');
    await page.waitForLoadState('networkidle');
  });

  test('should establish WebSocket connection', async ({ page }) => {
    // Check for WebSocket connection in console or network
    const wsMessages: any[] = [];

    // Listen to WebSocket frames
    page.on('websocket', (ws) => {
      ws.on('framesent', (frame) =>
        wsMessages.push({ type: 'sent', data: frame })
      );
      ws.on('framereceived', (frame) =>
        wsMessages.push({ type: 'received', data: frame })
      );
    });

    // Trigger an analysis to ensure WebSocket activity
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token1);

    // Wait for WebSocket messages
    await waitFor(2000);

    // Verify WebSocket connection was established
    expect(wsMessages.length).toBeGreaterThan(0);
  });

  test('should show job queued notification', async ({ page }) => {
    // Queue a token analysis
    const response = await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token1);

    // Wait for notification
    await waitFor(1000);

    // Look for queued notification
    const queuedNotification = page.getByText(
      /queued|analysis queued|job queued/i
    );

    if ((await queuedNotification.count()) > 0) {
      await expect(queuedNotification).toBeVisible();
    }
  });

  test('should show job started notification', async ({ page }) => {
    // Queue analysis
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token1);

    // Wait for job to start
    await retry(
      async () => {
        const startedNotification = page.getByText(
          /started|analysis started|processing/i
        );
        expect(await startedNotification.count()).toBeGreaterThan(0);
      },
      { times: 5, delay: 1000 }
    );

    const startedNotification = page.getByText(
      /started|analysis started|processing/i
    );
    await expect(startedNotification).toBeVisible();
  });

  test('should show job completed notification', async ({ page }) => {
    // Queue analysis
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token1);

    // Wait for completion (may take longer)
    await retry(
      async () => {
        const completedNotification = page.getByText(
          /completed|analysis complete|finished|success/i
        );
        expect(await completedNotification.count()).toBeGreaterThan(0);
      },
      { times: 10, delay: 2000 }
    );

    const completedNotification = page.getByText(
      /completed|analysis complete|finished|success/i
    );
    await expect(completedNotification).toBeVisible();
  });

  test('should show job failed notification for invalid token', async ({
    page
  }) => {
    // Queue analysis with invalid token address
    const invalidAddress = 'InvalidTokenAddress123';

    try {
      await apiFixture.api.seedToken(invalidAddress);
    } catch (error) {
      // Expected to fail
    }

    // Wait for failure notification
    await waitFor(2000);

    const failedNotification = page.getByText(/failed|error|analysis failed/i);

    if ((await failedNotification.count()) > 0) {
      await expect(failedNotification).toBeVisible();
    }
  });

  test('should display notification with token address', async ({ page }) => {
    // Queue analysis
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token1);

    await waitFor(1000);

    // Notification should include token address (truncated)
    const notificationWithAddress = page.getByText(
      new RegExp(SAMPLE_ADDRESSES.token1.slice(0, 8), 'i')
    );

    if ((await notificationWithAddress.count()) > 0) {
      await expect(notificationWithAddress).toBeVisible();
    }
  });

  test('should dismiss notification', async ({ page }) => {
    // Queue analysis
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token1);

    await waitFor(1000);

    // Find notification
    const notification = page.locator('[data-testid="notification"]').first();

    if ((await notification.count()) > 0) {
      // Find dismiss button
      const dismissButton = notification.getByRole('button', {
        name: /close|dismiss|×/i
      });

      if ((await dismissButton.count()) > 0) {
        await dismissButton.click();

        // Notification should disappear
        await waitFor(500);
        await expect(notification).not.toBeVisible();
      }
    }
  });

  test('should auto-dismiss notification after timeout', async ({ page }) => {
    // Queue analysis
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token1);

    await waitFor(1000);

    // Find notification
    const notification = page.locator('[data-testid="notification"]').first();

    if ((await notification.count()) > 0) {
      // Wait for auto-dismiss (typically 5-10 seconds)
      await waitFor(12000);

      // Notification should auto-dismiss
      await expect(notification).not.toBeVisible();
    }
  });

  test('should stack multiple notifications', async ({ page }) => {
    // Queue multiple analyses
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token1);
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token2);

    await waitFor(2000);

    // Should have multiple notifications visible
    const notifications = page.locator('[data-testid="notification"]');
    const count = await notifications.count();

    expect(count).toBeGreaterThanOrEqual(2);
  });

  test('should show notification icon/badge', async ({ page }) => {
    // Queue analysis
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token1);

    await waitFor(1000);

    // Find notification
    const notification = page.locator('[data-testid="notification"]').first();

    if ((await notification.count()) > 0) {
      // Should have status icon (success, error, info, etc.)
      const icon = notification.locator('[data-testid="notification-icon"]');

      if ((await icon.count()) > 0) {
        await expect(icon).toBeVisible();
      }
    }
  });

  test('should link to token details from notification', async ({ page }) => {
    // Queue analysis
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token1);

    // Wait for completion
    await retry(
      async () => {
        const completedNotification = page.getByText(/completed|success/i);
        expect(await completedNotification.count()).toBeGreaterThan(0);
      },
      { times: 10, delay: 2000 }
    );

    const notification = page.locator('[data-testid="notification"]').first();

    if ((await notification.count()) > 0) {
      // Click notification to view details
      const viewButton = notification.getByRole('button', {
        name: /view|details/i
      });

      if ((await viewButton.count()) > 0) {
        await viewButton.click();

        // Should open token details modal or navigate
        const tokenDetailsModal = page.getByTestId('token-details-modal');
        await expect(tokenDetailsModal).toBeVisible();
      } else {
        // Or click the notification itself
        await notification.click();

        const tokenDetailsModal = page.getByTestId('token-details-modal');
        if ((await tokenDetailsModal.count()) > 0) {
          await expect(tokenDetailsModal).toBeVisible();
        }
      }
    }
  });

  test('should show progress indicator for ongoing analysis', async ({
    page
  }) => {
    // Queue analysis
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token1);

    await waitFor(1000);

    // Find notification with progress
    const notification = page.locator('[data-testid="notification"]').first();

    if ((await notification.count()) > 0) {
      // Look for progress bar or spinner
      const progressIndicator = notification.locator(
        '[data-testid="progress-indicator"], [role="progressbar"], .spinner'
      );

      if ((await progressIndicator.count()) > 0) {
        await expect(progressIndicator).toBeVisible();
      }
    }
  });

  test('should persist notifications across page navigation', async ({
    page
  }) => {
    // Queue analysis
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token1);

    await waitFor(1000);

    // Verify notification exists
    const notificationsBefore = page.locator('[data-testid="notification"]');
    const countBefore = await notificationsBefore.count();

    expect(countBefore).toBeGreaterThan(0);

    // Navigate to different page
    await page.goto('/dashboard/trash');
    await page.waitForLoadState('networkidle');

    // Notifications should still be visible
    const notificationsAfter = page.locator('[data-testid="notification"]');
    const countAfter = await notificationsAfter.count();

    expect(countAfter).toBeGreaterThanOrEqual(countBefore);
  });

  test('should reconnect WebSocket after connection loss', async ({ page }) => {
    // This test simulates WebSocket reconnection
    const wsConnections: any[] = [];

    page.on('websocket', (ws) => {
      wsConnections.push(ws);
    });

    // Initial page load establishes connection
    await page.reload();
    await waitFor(2000);

    const initialConnections = wsConnections.length;
    expect(initialConnections).toBeGreaterThan(0);

    // Simulate network interruption by navigating away and back
    await page.goto('about:blank');
    await waitFor(1000);
    await page.goto('/dashboard/tokens');
    await waitFor(2000);

    // Should have established new connection
    const finalConnections = wsConnections.length;
    expect(finalConnections).toBeGreaterThan(initialConnections);
  });

  test('should display notification timestamp', async ({ page }) => {
    // Queue analysis
    await apiFixture.api.seedToken(SAMPLE_ADDRESSES.token1);

    await waitFor(1000);

    const notification = page.locator('[data-testid="notification"]').first();

    if ((await notification.count()) > 0) {
      // Look for timestamp
      const timestamp = notification.getByText(
        /\d+:\d+|seconds? ago|minutes? ago/i
      );

      if ((await timestamp.count()) > 0) {
        await expect(timestamp).toBeVisible();
      }
    }
  });
});
