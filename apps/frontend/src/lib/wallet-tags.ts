/**
 * Wallet Tag Constants — 3-Tier System
 *
 * Single source of truth for wallet tag definitions.
 *
 * Tier 1: Auto-tags from Helius API data (computed during enrichment)
 * Tier 2: Computed tags from Meridinate's own database (no API calls)
 * Tier 3: Manual tags for human judgment
 */

// ============================================================================
// Tier Definitions
// ============================================================================

export const WALLET_TAG_TIERS = {
  1: {
    label: 'Auto (Helius)',
    tags: [
      'Exchange',
      'Protocol',
      'Cluster',
      'Fresh at Entry (<1h)',
      'Fresh at Entry (<24h)',
      'Fresh at Entry (<3d)',
      'Fresh at Entry (<7d)',
      'High SOL Balance',
      'Low Value',
      'Active Trader',
      'Holder',
      'Deployer',
      'Serial Deployer',
      'Winning Deployer',
      'Rug Deployer',
      'High-Value Deployer',
      'Correlated Wallet',
      'Deployer Network',
      'Lightning Buyer',
      'Sniper Bot',
      'Automated (Nozomi)',
      'Bundled (Jito)'
    ] as const
  },
  2: {
    label: 'Computed',
    tags: [
      'Consistent Winner',
      'Consistent Loser',
      'Diversified',
      'Sniper',
      'Lightning Buyer'
    ] as const
  },
  3: {
    label: 'Manual',
    tags: ['Insider', 'KOL', 'Watchlist'] as const
  }
} as const;

export type Tier1Tag = (typeof WALLET_TAG_TIERS)[1]['tags'][number];
export type Tier2Tag = (typeof WALLET_TAG_TIERS)[2]['tags'][number];
export type Tier3Tag = (typeof WALLET_TAG_TIERS)[3]['tags'][number];
export type WalletTag = Tier1Tag | Tier2Tag | Tier3Tag;

/** Only manual tags can be added/removed by the user */
export const MANUAL_WALLET_TAGS = WALLET_TAG_TIERS[3].tags;

/** All known tags across all tiers */
export const ALL_WALLET_TAGS = [
  ...WALLET_TAG_TIERS[1].tags,
  ...WALLET_TAG_TIERS[2].tags,
  ...WALLET_TAG_TIERS[3].tags
];

// ============================================================================
// Backwards Compatibility
// ============================================================================

/**
 * @deprecated Use MANUAL_WALLET_TAGS instead
 */
export const ADDITIONAL_TAGS = MANUAL_WALLET_TAGS;
export type AdditionalTag = Tier3Tag;
export const ADDITIONAL_TAGS_DISPLAY = MANUAL_WALLET_TAGS.map(
  (tag) => tag.charAt(0).toUpperCase() + tag.slice(1)
);

// ============================================================================
// Tag Styling
// ============================================================================

export function getTagTier(tag: string): 1 | 2 | 3 {
  if ((WALLET_TAG_TIERS[1].tags as readonly string[]).includes(tag)) return 1;
  if ((WALLET_TAG_TIERS[2].tags as readonly string[]).includes(tag)) return 2;
  return 3;
}

export function getTagStyle(tag: string): { bg: string; text: string } {
  const tier = getTagTier(tag);

  // Tier 1: Blue tones (auto from Helius)
  if (tier === 1) {
    if (tag === 'High SOL Balance') return { bg: 'bg-emerald-500/20', text: 'text-emerald-400' };
    if (tag === 'Low Value') return { bg: 'bg-zinc-500/20', text: 'text-zinc-400' };
    if (tag === 'Cluster') return { bg: 'bg-amber-500/20', text: 'text-amber-400' };
    if (tag === 'Exchange') return { bg: 'bg-cyan-500/20', text: 'text-cyan-400' };
    if (tag === 'Protocol') return { bg: 'bg-indigo-500/20', text: 'text-indigo-400' };
    if (tag === 'Fresh at Entry (<1h)') return { bg: 'bg-red-500/20', text: 'text-red-400' };
    if (tag === 'Fresh at Entry (<24h)') return { bg: 'bg-orange-500/20', text: 'text-orange-400' };
    if (tag === 'Fresh at Entry (<3d)') return { bg: 'bg-amber-500/20', text: 'text-amber-300' };
    if (tag === 'Fresh at Entry (<7d)') return { bg: 'bg-yellow-500/20', text: 'text-yellow-400' };
    if (tag === 'Deployer') return { bg: 'bg-purple-500/20', text: 'text-purple-400' };
    if (tag === 'Serial Deployer') return { bg: 'bg-fuchsia-500/20', text: 'text-fuchsia-400' };
    if (tag === 'Winning Deployer') return { bg: 'bg-green-500/20', text: 'text-green-400' };
    if (tag === 'Rug Deployer') return { bg: 'bg-red-500/20', text: 'text-red-400' };
    if (tag === 'High-Value Deployer') return { bg: 'bg-amber-500/20', text: 'text-amber-400' };
    if (tag === 'Correlated Wallet') return { bg: 'bg-orange-500/20', text: 'text-orange-400' };
    if (tag === 'Deployer Network') return { bg: 'bg-rose-500/20', text: 'text-rose-400' };
    if (tag === 'Sniper Bot') return { bg: 'bg-red-600/20', text: 'text-red-500' };
    if (tag === 'Automated (Nozomi)') return { bg: 'bg-cyan-600/20', text: 'text-cyan-400' };
    if (tag === 'Bundled (Jito)') return { bg: 'bg-orange-600/20', text: 'text-orange-400' };
    return { bg: 'bg-blue-500/20', text: 'text-blue-400' };
  }

  // Tier 2: Green/amber tones (computed from Meridinate data)
  if (tier === 2) {
    if (tag === 'Consistent Winner') return { bg: 'bg-green-500/20', text: 'text-green-400' };
    if (tag === 'Consistent Loser') return { bg: 'bg-red-500/20', text: 'text-red-400' };
    if (tag === 'Sniper') return { bg: 'bg-purple-500/20', text: 'text-purple-400' };
    if (tag === 'Lightning Buyer') return { bg: 'bg-sky-500/20', text: 'text-sky-400' };
    return { bg: 'bg-teal-500/20', text: 'text-teal-400' };
  }

  // Tier 3: Purple tones (manual)
  if (tag === 'KOL') return { bg: 'bg-pink-500/20', text: 'text-pink-400' };
  if (tag === 'Insider') return { bg: 'bg-rose-500/20', text: 'text-rose-400' };
  return { bg: 'bg-violet-500/20', text: 'text-violet-400' };
}

export function isAdditionalTag(tag: string): boolean {
  return ALL_WALLET_TAGS.includes(tag as WalletTag);
}
