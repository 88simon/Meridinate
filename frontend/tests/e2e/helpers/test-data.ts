/**
 * Test Data Helpers
 * Provides sample Solana addresses and test data
 */

// Valid Solana address format (base58, 32-44 chars)
export const SAMPLE_ADDRESSES = {
  // USDC token address (real)
  token1: 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',

  // SOL address (real)
  token2: 'So11111111111111111111111111111111111111112',

  // Sample wallet addresses (for testing - not real wallets with funds)
  wallet1: '7UX2i7SucgLMQcfZ75s3VXmZZY4YRUyJN9X1RgfMoDUi',
  wallet2: '5ZiE3vAkrdXBgyFL7KqG3RoEGBws4CjRcXVbABDLZTgx',
  wallet3: 'DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK'
};

export const SAMPLE_TAGS = [
  'whale',
  'dev',
  'suspicious',
  'high-volume',
  'insider'
];

export const SAMPLE_WATCHLIST_LABELS = [
  'Test Wallet Alpha',
  'Test Wallet Beta',
  'Known Whale',
  'Dev Team Member'
];

/**
 * Generates a mock token response for seeding
 */
export function generateMockTokenData(tokenAddress: string) {
  return {
    token_address: tokenAddress,
    name: `Test Token ${tokenAddress.slice(0, 8)}`,
    symbol: 'TEST'
    // Add more fields as needed based on your Token schema
  };
}

/**
 * Wait helper for async operations
 */
export async function waitFor(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Retry helper for flaky operations
 */
export async function retry<T>(
  fn: () => Promise<T>,
  options: { times?: number; delay?: number } = {}
): Promise<T> {
  const { times = 3, delay = 1000 } = options;

  for (let i = 0; i < times; i++) {
    try {
      return await fn();
    } catch (error) {
      if (i === times - 1) throw error;
      await waitFor(delay);
    }
  }

  throw new Error('Retry failed');
}
