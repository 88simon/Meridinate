/**
 * API Fixtures for E2E Tests
 * Provides helpers for interacting with the FastAPI backend
 */

const API_BASE_URL = 'http://localhost:5003';

export interface ApiFixture {
  api: {
    baseUrl: string;
    health: () => Promise<Response>;
    clearDatabase: () => Promise<void>;
    seedToken: (tokenAddress: string) => Promise<any>;
    registerWatchlistAddress: (address: string, label?: string) => Promise<any>;
    clearWatchlist: () => Promise<void>;
    addTag: (walletAddress: string, tag: string) => Promise<any>;
    removeTag: (walletAddress: string, tag: string) => Promise<any>;
  };
}

export const apiFixture: ApiFixture = {
  api: {
    baseUrl: API_BASE_URL,

    async health() {
      return fetch(`${API_BASE_URL}/health`);
    },

    async clearDatabase() {
      // Clear tokens by deleting all from trash permanently
      const tokensRes = await fetch(`${API_BASE_URL}/api/tokens/history`);
      const tokensData = await tokensRes.json();

      for (const token of tokensData.tokens || []) {
        // Soft delete first
        await fetch(`${API_BASE_URL}/api/tokens/${token.id}`, {
          method: 'DELETE'
        });
        // Permanent delete
        await fetch(`${API_BASE_URL}/api/tokens/${token.id}/permanent`, {
          method: 'DELETE'
        });
      }
    },

    async seedToken(tokenAddress: string) {
      const response = await fetch(`${API_BASE_URL}/analyze/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token_address: tokenAddress })
      });
      return response.json();
    },

    async registerWatchlistAddress(address: string, label?: string) {
      const response = await fetch(`${API_BASE_URL}/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          address,
          label: label || `Test ${address.slice(0, 8)}`
        })
      });
      return response.json();
    },

    async clearWatchlist() {
      await fetch(`${API_BASE_URL}/clear`, {
        method: 'POST'
      });
    },

    async addTag(walletAddress: string, tag: string) {
      const response = await fetch(
        `${API_BASE_URL}/wallets/${walletAddress}/tags`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ tag })
        }
      );
      return response.json();
    },

    async removeTag(walletAddress: string, tag: string) {
      const response = await fetch(
        `${API_BASE_URL}/wallets/${walletAddress}/tags/${tag}`,
        {
          method: 'DELETE'
        }
      );
      return response.json();
    }
  }
};
