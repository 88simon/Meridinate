import { NavItem } from '@/types';

export type Product = {
  photo_url: string;
  name: string;
  description: string;
  created_at: string;
  price: number;
  id: number;
  category: string;
  updated_at: string;
};

//Info: The following data is used for the sidebar navigation.
// Order: Wallet Leaderboard (HOME), Token Leaderboard, Token Pipeline, Codex (button), Trash, Settings (modal)
export const navItems: NavItem[] = [
  {
    title: 'Wallet Leaderboard',
    url: '/dashboard/wallets',
    icon: 'tracking',
    shortcut: ['w', 'w'],
    isActive: false,
    items: []
  },
  {
    title: 'Token Leaderboard',
    url: '/dashboard/token-leaderboard',
    icon: 'chart',
    shortcut: ['l', 'l'],
    isActive: false,
    items: []
  },
  {
    title: 'Quick DD',
    url: '/dashboard/quick-dd',
    icon: 'search',
    shortcut: ['q', 'q'],
    isActive: false,
    items: []
  },
  {
    title: 'Rug Analysis',
    url: '/dashboard/rug-analysis',
    icon: 'shield',
    shortcut: ['r', 'a'],
    isActive: false,
    items: []
  },
  {
    title: 'Trash',
    url: '/dashboard/trash',
    icon: 'trash',
    shortcut: ['d', 'd'],
    isActive: false,
    items: []
  }
];

export interface SaleUser {
  id: number;
  name: string;
  email: string;
  amount: string;
  image: string;
  initials: string;
}

export const recentSalesData: SaleUser[] = [
  {
    id: 1,
    name: 'Olivia Martin',
    email: 'olivia.martin@email.com',
    amount: '+$1,999.00',
    image: 'https://api.slingacademy.com/public/sample-users/1.png',
    initials: 'OM'
  },
  {
    id: 2,
    name: 'Jackson Lee',
    email: 'jackson.lee@email.com',
    amount: '+$39.00',
    image: 'https://api.slingacademy.com/public/sample-users/2.png',
    initials: 'JL'
  },
  {
    id: 3,
    name: 'Isabella Nguyen',
    email: 'isabella.nguyen@email.com',
    amount: '+$299.00',
    image: 'https://api.slingacademy.com/public/sample-users/3.png',
    initials: 'IN'
  },
  {
    id: 4,
    name: 'William Kim',
    email: 'will@email.com',
    amount: '+$99.00',
    image: 'https://api.slingacademy.com/public/sample-users/4.png',
    initials: 'WK'
  },
  {
    id: 5,
    name: 'Sofia Davis',
    email: 'sofia.davis@email.com',
    amount: '+$39.00',
    image: 'https://api.slingacademy.com/public/sample-users/5.png',
    initials: 'SD'
  }
];
