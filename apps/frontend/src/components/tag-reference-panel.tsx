'use client';

import { usePathname } from 'next/navigation';
import { X, ChevronDown } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface Props {
  open: boolean;
  onClose: () => void;
}

function Section({ title, defaultOpen = false, children }: { title: string; defaultOpen?: boolean; children: React.ReactNode }) {
  return (
    <details open={defaultOpen} className='group'>
      <summary className='flex items-center gap-1 cursor-pointer text-[10px] font-semibold uppercase text-muted-foreground hover:text-foreground select-none'>
        <ChevronDown className='h-2.5 w-2.5 transition-transform group-open:rotate-0 -rotate-90' />
        {title}
      </summary>
      <div className='mt-1.5 space-y-1.5 text-[10px]'>
        {children}
      </div>
    </details>
  );
}

function Entry({ name, color, desc }: { name: string; color: string; desc: string }) {
  return (
    <div><span className={`${color} font-medium`}>{name}</span> <span className='text-muted-foreground'>— {desc}</span></div>
  );
}

function WalletReference() {
  return (
    <>
      <Section title='Behavioral' defaultOpen>
        <Entry name='Consistent Winner' color='text-green-400' desc='60%+ win rate with 3+ wins from real PnL' />
        <Entry name='Consistent Loser' color='text-red-400' desc='≤30% win rate with 3+ losses from real PnL' />
        <Entry name='Sniper' color='text-purple-400' desc='Consistently fast entry timing across multiple tokens' />
        <Entry name='Lightning Buyer' color='text-sky-400' desc='Buys within 60s of token creation on 3+ tokens' />
        <Entry name='Diversified' color='text-teal-400' desc='Trades across many tokens without concentrating' />
      </Section>

      <Section title='Infrastructure' defaultOpen>
        <Entry name='Automated (Nozomi)' color='text-cyan-400' desc="Tipped Temporal's Nozomi for priority tx landing" />
        <Entry name='Bundled (Jito)' color='text-orange-400' desc='Transaction included in a Jito bundle' />
        <Entry name='Sniper Bot' color='text-red-500' desc='Avg entry <30s on 5+ tokens, 80%+ under 60s. Excluded from scoring' />
      </Section>

      <Section title='Wallet Profile' defaultOpen>
        <Entry name='High SOL Balance' color='text-emerald-400' desc='Wallet holds significant SOL' />
        <Entry name='Fresh at Entry (<24h)' color='text-orange-400' desc='Wallet was <24h old when it first bought a token' />
        <Entry name='Fresh at Entry (<1h)' color='text-red-400' desc='Wallet was <1h old at first buy. Very suspicious' />
        <Entry name='Cluster' color='text-amber-400' desc='Shares a common funder with other early buyers (sybil signal)' />
        <Entry name='Correlated Wallet' color='text-orange-400' desc='Appears alongside the same wallets across 3+ tokens' />
      </Section>

      <Section title='Deployer'>
        <Entry name='Deployer' color='text-purple-400' desc='Created at least one token in our database' />
        <Entry name='Serial Deployer' color='text-fuchsia-400' desc='Created 3+ tokens' />
        <Entry name='Winning Deployer' color='text-green-400' desc='Deployed tokens that hit verified-win' />
        <Entry name='Rug Deployer' color='text-red-400' desc='Deployed tokens that rugged or lost 90%+' />
        <Entry name='Deployer Network' color='text-rose-400' desc='Deployers sharing the same funding source' />
      </Section>

      <Section title='Manual'>
        <Entry name='Insider' color='text-rose-400' desc='Manually tagged as suspected insider' />
        <Entry name='KOL' color='text-pink-400' desc='Manually tagged as Key Opinion Leader' />
        <Entry name='Watchlist' color='text-violet-400' desc='Manually added to your watchlist via Codex' />
      </Section>

      <Section title='Token Outcome Tiers'>
        <Entry name='100x / 50x / 25x' color='text-yellow-300' desc='Token ATH reached this multiplier' />
        <Entry name='10x' color='text-amber-400' desc='Token ATH hit 10x. Home run threshold' />
        <Entry name='5x / 3x' color='text-green-400' desc='Token ATH hit 5x or 3x original MC' />
        <Entry name='RUG' color='text-red-500' desc='Token dropped 95%+ within 1 hour' />
        <Entry name='90%' color='text-red-400' desc='Token lost 90%+ of value' />
        <Entry name='70%' color='text-orange-400' desc='Token lost 70-90% of value' />
        <Entry name='DEAD' color='text-red-500' desc='Token MC fell below $1,000' />
        <Entry name='STALE' color='text-zinc-400' desc='No verdict after 14 days' />
      </Section>

      <Section title='Column Reference'>
        <Entry name='Home Runs' color='text-foreground' desc='Tokens that hit 10x+ ATH' />
        <Entry name='Rugs' color='text-foreground' desc='Rug pulls + dead tokens' />
        <Entry name='Avg Entry' color='text-foreground' desc='Avg seconds after token creation when wallet buys' />
        <Entry name='Age' color='text-foreground' desc='Wallet age from first funding tx' />
        <Entry name='7D Hold' color='text-foreground' desc='Avg hold time for exits in last 7 days' />
        <Entry name='Win Rate' color='text-foreground' desc='Wins / total tokens with verdicts' />
      </Section>
    </>
  );
}

function TokenReference() {
  return (
    <>
      <Section title='Scores' defaultOpen>
        <Entry name='Composite' color='text-foreground' desc='Weighted avg of Momentum + Smart Money + inverted Risk. Higher = better' />
        <Entry name='Momentum' color='text-foreground' desc='MC growth, ATH proximity, liquidity health. 0-100' />
        <Entry name='Smart Money' color='text-foreground' desc='Consistent Winners, Snipers, High SOL Balance wallets buying early. 0-100' />
        <Entry name='Risk' color='text-foreground' desc='Mint/freeze authority, holder concentration, liquidity ratio, Meteora pools. 0-100, lower = safer' />
      </Section>

      <Section title='Safety & Fees' defaultOpen>
        <Entry name='Mint Authority' color='text-foreground' desc='Revoked = safe. Active = creator can print more tokens' />
        <Entry name='Freeze Authority' color='text-foreground' desc='None = safe. Active = creator can freeze your tokens' />
        <Entry name='Cashback' color='text-green-400' desc='Fees go to traders (lower rug incentive)' />
        <Entry name='Creator Fee' color='text-amber-400' desc='Fees go to deployer' />
      </Section>

      <Section title='Risk Signals' defaultOpen>
        <Entry name='Fresh %' color='text-foreground' desc='% of early buyers that were fresh wallets (<7 days old). Higher = suspicious' />
        <Entry name='Fresh@Deploy' color='text-foreground' desc='Fresh wallets buying within 60s of creation. Format: fresh/total' />
        <Entry name='Supply Control' color='text-foreground' desc='Score 0-100. Fresh wallets near deploy + cluster overlap + supply held by fresh wallets' />
        <Entry name='Bundle Clusters' color='text-foreground' desc='Wallets buying at exact same second. Format: clusters/largest cluster size' />
        <Entry name='Stealth Holders' color='text-foreground' desc='Top holders with suspiciously small buys. Holds 1%+ supply but spent <$200' />
      </Section>

      <Section title='Meteora Detection'>
        <Entry name='Meteora LP' color='text-purple-400' desc='A Meteora DLMM pool exists for this PumpFun token — unusual' />
        <Entry name='Meteora Stealth Sell' color='text-red-400' desc='Pool creator is linked to deployer/insiders. Stealth exit via LP provision' />
        <Entry name='add_single' color='text-orange-400' desc='Tokens deposited without SOL = sell wall setup' />
        <Entry name='remove' color='text-red-400' desc='Tokens/SOL withdrawn from pool = profit extracted' />
      </Section>

      <Section title='Verdicts'>
        <Entry name='Verified Win' color='text-green-400' desc='ATH ≥ 3x + still at break-even, OR ATH ≥ 1.5x + current ≥ 1.5x' />
        <Entry name='Verified Loss' color='text-red-400' desc='90%+ drop (6h gate), 70%+ (72h), dead (<$1k), or stale (14d)' />
        <Entry name='Win Multiplier' color='text-yellow-300' desc='Highest ATH tier: 3x, 5x, 10x, 25x, 50x, 100x' />
      </Section>

      <Section title='Signals Column'>
        <Entry name='↑/↓ Concentration' color='text-foreground' desc='Holder velocity — top holder % changing fast' />
        <Entry name='High Volatility' color='text-amber-400' desc='MC coefficient of variation > 40' />
        <Entry name='Recovery' color='text-green-400' desc='MC bounced back from a dip' />
        <Entry name='Smart Bullish/Bearish' color='text-foreground' desc='Net smart money flow direction' />
        <Entry name='Deployer Holding' color='text-amber-400' desc='Deployer is still a top holder' />
      </Section>

      <Section title='Column Reference'>
        <Entry name='MC' color='text-foreground' desc='Current market cap + % change + at-scan MC' />
        <Entry name='ATH' color='text-foreground' desc='All-time high market cap' />
        <Entry name='Liquidity' color='text-foreground' desc='USD liquidity in primary pool' />
        <Entry name='Wallets' color='text-foreground' desc='Early buyer count from analysis' />
        <Entry name='Top Holder' color='text-foreground' desc='% of supply held by single largest wallet' />
        <Entry name='Deployer' color='text-foreground' desc='Win rate + tokens deployed by this deployer' />
        <Entry name='PnL' color='text-foreground' desc='Aggregate realized PnL from all wallets with real data' />
      </Section>
    </>
  );
}

function RttfReference() {
  return (
    <>
      <Section title='Conviction Labels' defaultOpen>
        <Entry name='HIGH CONVICTION' color='text-green-400' desc='Deployer has win history + smart money wallets bought + passed safety checks' />
        <Entry name='WATCHING' color='text-yellow-400' desc='Some positive signals but not enough for high conviction' />
        <Entry name='WEAK' color='text-muted-foreground' desc='MC below threshold at watch window close' />
        <Entry name='REJECTED' color='text-red-400' desc='Failed safety checks (mint active, freeze, suspicious deployer)' />
      </Section>

      <Section title='Crime Coin Detection' defaultOpen>
        <Entry name='Watch Window' color='text-foreground' desc='Seconds after token creation to monitor for suspicious activity (configurable)' />
        <Entry name='Bundling' color='text-foreground' desc='Multiple wallets buying in the same block at creation' />
        <Entry name='Fresh Buyers' color='text-foreground' desc='Wallets created recently that buy immediately — possible sybils' />
        <Entry name='Funding Convergence' color='text-foreground' desc='Multiple early buyers sharing the same funding source' />
      </Section>

      <Section title='Follow-Up Tracking'>
        <Entry name='Trajectory' color='text-foreground' desc='MC over time after watch window. Adapts: extends on uptrend, cuts on flatline' />
        <Entry name='Duration' color='text-foreground' desc='Max tracking time after watch window (configurable, 30min-8hrs)' />
        <Entry name='Check Interval' color='text-foreground' desc='How often to poll DexScreener for MC updates (free)' />
      </Section>

      <Section title='Pipeline Stages'>
        <Entry name='Stage 0' color='text-foreground' desc='Real-Time Detection — Helius WebSocket, zero credits' />
        <Entry name='Stage 0.5' color='text-foreground' desc='Follow-Up Tracker — DexScreener MC polling, free' />
        <Entry name='Stage 1' color='text-foreground' desc='Token Discovery — DexScreener search, free' />
        <Entry name='Stage 2' color='text-foreground' desc='Token Analysis — Helius early buyer extraction, ~30-80 credits' />
        <Entry name='Stage 3' color='text-foreground' desc='MC Tracker — DexScreener polling, auto-verdicts, free' />
        <Entry name='Stage 4' color='text-foreground' desc='Token Scorer — momentum + smart money + risk, 0-3 credits' />
        <Entry name='Stage 5' color='text-foreground' desc='Position Tracker — wallet balance monitoring, ~10 credits/check' />
      </Section>

      <Section title='Accuracy Dashboard'>
        <Entry name='Conviction Accuracy' color='text-foreground' desc='% of HIGH CONVICTION tokens that achieved verified-win' />
        <Entry name='Sample Size' color='text-foreground' desc='Tokens that completed their lifecycle (birth → verdict)' />
      </Section>
    </>
  );
}

export function TagReferencePanel({ open, onClose }: Props) {
  const pathname = usePathname();
  const isTokenPage = pathname?.includes('token-leaderboard');
  const isRttfPage = pathname?.includes('/dashboard/tokens');

  if (!open) return null;

  const title = isTokenPage ? 'Token Reference' : isRttfPage ? 'RTTF Reference' : 'Tag Reference';

  return (
    <div className='fixed left-16 top-0 z-40 flex h-full'>
      <div className='w-60 h-full border-r bg-background shadow-xl overflow-y-auto animate-in slide-in-from-left duration-200'>
        <div className='sticky top-0 bg-background z-10 flex items-center justify-between border-b px-3 py-2'>
          <h3 className='text-xs font-semibold'>{title}</h3>
          <Button variant='ghost' size='sm' onClick={onClose} className='h-6 w-6 p-0'>
            <X className='h-3 w-3' />
          </Button>
        </div>
        <div className='p-3 space-y-3'>
          {isTokenPage ? <TokenReference /> : isRttfPage ? <RttfReference /> : <WalletReference />}
        </div>
      </div>
    </div>
  );
}
