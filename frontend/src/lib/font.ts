import { Geist, Geist_Mono, Inter } from 'next/font/google';

import { cn } from '@/lib/utils';

// Optimized: Reduced from 6 fonts to 3 essential fonts for faster loading
const fontSans = Geist({
  subsets: ['latin'],
  variable: '--font-sans',
  display: 'swap' // Optimize font loading
});

const fontMono = Geist_Mono({
  subsets: ['latin'],
  variable: '--font-mono',
  display: 'swap'
});

const fontInter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
  display: 'swap'
});

export const fontVariables = cn(
  fontSans.variable,
  fontMono.variable,
  fontInter.variable
);
