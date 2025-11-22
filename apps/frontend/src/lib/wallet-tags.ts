/**
 * Wallet Tag Constants
 *
 * This file serves as the single source of truth for wallet tag definitions.
 * All components that work with additional tags should import from here
 * to ensure consistency across the application.
 */

/**
 * Additional tags that appear in:
 * - Additional Tags Popover (popover in Tags column)
 * - Batch Tag Management (popup when wallets are selected)
 * - Wallet Tags filtering logic
 *
 * These tags are managed separately from regular user-created tags.
 * They represent special wallet categorizations.
 */
export const ADDITIONAL_TAGS = [
  'bot',
  'whale',
  'insider',
  'gunslinger',
  'gambler'
] as const;

/**
 * Type for additional tag values
 */
export type AdditionalTag = (typeof ADDITIONAL_TAGS)[number];

/**
 * Display names for additional tags (capitalized for UI)
 */
export const ADDITIONAL_TAGS_DISPLAY = ADDITIONAL_TAGS.map(
  (tag) => tag.charAt(0).toUpperCase() + tag.slice(1)
);

/**
 * Helper function to check if a tag is an additional tag
 */
export function isAdditionalTag(tag: string): boolean {
  return ADDITIONAL_TAGS.includes(tag.toLowerCase() as AdditionalTag);
}
