export interface ApiSettings {
  transactionLimit: number;
  minUsdFilter: number;
  walletCount: number;
  apiRateDelay: number;
  maxCreditsPerAnalysis: number;
  maxRetries: number;
  bypassLimits?: boolean;
  // Intel Agent settings
  intelMaxTokens?: number;
  intelHousekeeperMaxTokens?: number;
  intelForensicsWalletCount?: number;
  intelModel?: string;
}
