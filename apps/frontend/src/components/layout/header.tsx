import React from 'react';
import { Separator } from '../ui/separator';
import { Breadcrumbs } from '../breadcrumbs';
import SearchInput from '../search-input';
import { UserNav } from './user-nav';
import { ThemeSelector } from '../theme-selector';
import { ModeToggle } from './ThemeToggle/theme-toggle';
import CtaGithub from './cta-github';
import { MeridinateLogo } from '../meridinate-logo';

export default function Header() {
  return (
    <header className='flex h-16 shrink-0 items-center justify-between gap-2 transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-12'>
      <div className='flex items-center gap-2 px-4'>
        <div className='flex items-center gap-2'>
          <MeridinateLogo className='h-8 w-8 shrink-0' />
          <div className='flex flex-col'>
            <span className='text-base font-semibold'>Meridinate</span>
            <span className='text-muted-foreground text-[10px] tracking-wide uppercase'>
              Blockchain Intelligence Desk
            </span>
          </div>
        </div>
        <Separator orientation='vertical' className='mx-2 h-8' />
        <Breadcrumbs />
      </div>

      <div className='flex items-center gap-2 px-4'>
        <CtaGithub />
        <div className='hidden md:flex'>
          <SearchInput />
        </div>
        <UserNav />
        <ModeToggle />
        <ThemeSelector />
      </div>
    </header>
  );
}
