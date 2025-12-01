export interface ApiSettings {
  transactionLimit: number;
  minUsdFilter: number;
  walletCount: number;
  apiRateDelay: number;
  maxCreditsPerAnalysis: number;
  maxRetries: number;
  bypassLimits?: boolean;
}

export interface WebhookInfo {
  webhookID: string;
  webhookURL: string;
  accountAddresses?: string[];
  webhookType?: string;
}
