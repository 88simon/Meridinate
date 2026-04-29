import React from 'react';
import { Separator } from '../ui/separator';
import { Breadcrumbs } from '../breadcrumbs';
import SearchInput from '../search-input';
import { ThemeSelector } from '../theme-selector';
import { ModeToggle } from './ThemeToggle/theme-toggle';
import { MeridinateLogo } from '../meridinate-logo';
import { GlobalStatusBar } from './global-status-bar';

export default function Header() {
  return (
    <header className='flex shrink-0 flex-col border-b transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-12'>
      {/* Top row: Logo + breadcrumb + nav */}
      <div className='flex h-12 items-center justify-between gap-2 px-4'>
        <div className='flex items-center gap-2'>
          <div className='flex items-center gap-2'>
            <MeridinateLogo className='h-7 w-7 shrink-0' />
            <div className='flex flex-col'>
              <span className='text-sm font-semibold leading-tight'>Meridinate</span>
              <span className='text-muted-foreground text-[9px] tracking-wide uppercase leading-tight'>
                Blockchain Intelligence Desk
              </span>
            </div>
          </div>
          <Separator orientation='vertical' className='mx-2 h-6' />
          <Breadcrumbs />
        </div>

        <div className='flex items-center gap-2'>
          <div className='hidden md:flex'>
            <SearchInput />
          </div>
          <ModeToggle />
          <ThemeSelector />
        </div>
      </div>

      {/* Status bar row */}
      <div className='flex h-12 items-center px-4 bg-muted/30'>
        <GlobalStatusBar />
      </div>
    </header>
  );
}
