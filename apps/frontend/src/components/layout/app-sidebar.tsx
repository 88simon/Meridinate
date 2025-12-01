'use client';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger
} from '@/components/ui/collapsible';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger
} from '@/components/ui/dropdown-menu';
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  SidebarRail,
  SidebarTrigger
} from '@/components/ui/sidebar';
import { UserAvatarProfile } from '@/components/user-avatar-profile';
import { navItems } from '@/constants/data';
import { useMediaQuery } from '@/hooks/use-media-query';
import { useUser } from '@clerk/nextjs';
import { MasterControlModal } from '@/components/master-control-modal';
import { useApiSettings } from '@/contexts/ApiSettingsContext';
import {
  IconChevronRight,
  IconChevronsDown,
  IconTags,
  IconAdjustments,
  IconClock
} from '@tabler/icons-react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import * as React from 'react';
import { Icons } from '../icons';

interface AppSidebarProps {
  onCodexToggle?: () => void;
  onSchedulerToggle?: () => void;
}

export default function AppSidebar({
  onCodexToggle,
  onSchedulerToggle
}: AppSidebarProps) {
  const pathname = usePathname();
  const { isOpen } = useMediaQuery();
  const { user } = useUser();
  const [showSettings, setShowSettings] = React.useState(false);
  const { apiSettings, setApiSettings, defaultApiSettings } = useApiSettings();

  React.useEffect(() => {
    // Side effects based on sidebar state changes
  }, [isOpen]);

  return (
    <Sidebar collapsible='icon'>
      <SidebarContent className='flex flex-col overflow-x-hidden'>
        <SidebarGroup>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton asChild tooltip='Toggle Sidebar'>
                <SidebarTrigger className='w-full justify-start' />
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarGroup>
        <div className='flex flex-1 flex-col justify-center'>
          <SidebarGroup>
            <SidebarGroupLabel>Overview</SidebarGroupLabel>
            <SidebarMenu>
              {/* Render nav items with Codex inserted between Scanned Tokens and Trash */}
              {navItems.map((item, index) => {
                const Icon = item.icon ? Icons[item.icon] : Icons.logo;
                const hasSubItems = item?.items && item?.items?.length > 0;

                // Render the nav item
                const navItem = hasSubItems ? (
                  <Collapsible
                    key={item.title}
                    asChild
                    defaultOpen={item.isActive}
                    className='group/collapsible'
                  >
                    <SidebarMenuItem>
                      <CollapsibleTrigger asChild>
                        <SidebarMenuButton
                          tooltip={item.title}
                          isActive={pathname === item.url}
                        >
                          {item.icon && <Icon />}
                          <span>{item.title}</span>
                          <IconChevronRight className='ml-auto transition-transform duration-200 group-data-[state=open]/collapsible:rotate-90' />
                        </SidebarMenuButton>
                      </CollapsibleTrigger>
                      <CollapsibleContent>
                        <SidebarMenuSub>
                          {item.items?.map((subItem) => (
                            <SidebarMenuSubItem key={subItem.title}>
                              <SidebarMenuSubButton
                                asChild
                                isActive={pathname === subItem.url}
                              >
                                <Link href={subItem.url}>
                                  <span>{subItem.title}</span>
                                </Link>
                              </SidebarMenuSubButton>
                            </SidebarMenuSubItem>
                          ))}
                        </SidebarMenuSub>
                      </CollapsibleContent>
                    </SidebarMenuItem>
                  </Collapsible>
                ) : (
                  <SidebarMenuItem key={item.title}>
                    <SidebarMenuButton
                      asChild
                      tooltip={item.title}
                      isActive={pathname === item.url}
                    >
                      <Link href={item.url}>
                        <Icon />
                        <span>{item.title}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );

                // Insert Codex after Scanned Tokens (index 1)
                if (index === 1) {
                  return (
                    <React.Fragment key={item.title}>
                      {navItem}
                      <SidebarMenuItem key='codex'>
                        <SidebarMenuButton
                          onClick={onCodexToggle}
                          tooltip='Codex'
                        >
                          <IconTags />
                          <span>Codex</span>
                        </SidebarMenuButton>
                      </SidebarMenuItem>
                    </React.Fragment>
                  );
                }

                return navItem;
              })}

              {/* Scheduler panel toggle */}
              <SidebarMenuItem>
                <SidebarMenuButton
                  onClick={onSchedulerToggle}
                  tooltip='Scheduler'
                >
                  <IconClock />
                  <span>Scheduler</span>
                </SidebarMenuButton>
              </SidebarMenuItem>

              {/* Settings at the end */}
              <SidebarMenuItem>
                <MasterControlModal
                  open={showSettings}
                  onOpenChange={setShowSettings}
                  apiSettings={apiSettings}
                  setApiSettings={setApiSettings}
                  defaultApiSettings={defaultApiSettings}
                >
                  <SidebarMenuButton tooltip='Settings'>
                    <IconAdjustments />
                    <span>Settings</span>
                  </SidebarMenuButton>
                </MasterControlModal>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroup>
        </div>
      </SidebarContent>
      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <SidebarMenuButton
                  size='lg'
                  className='data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground'
                >
                  {user && (
                    <UserAvatarProfile
                      className='h-8 w-8 rounded-lg'
                      showInfo
                      user={user}
                    />
                  )}
                  <IconChevronsDown className='ml-auto size-4' />
                </SidebarMenuButton>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                className='w-(--radix-dropdown-menu-trigger-width) min-w-56 rounded-lg'
                side='bottom'
                align='end'
                sideOffset={4}
              >
                <DropdownMenuLabel className='p-0 font-normal'>
                  <div className='px-1 py-1.5'>
                    {user && (
                      <UserAvatarProfile
                        className='h-8 w-8 rounded-lg'
                        showInfo
                        user={user}
                      />
                    )}
                  </div>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem disabled>
                  <span className='text-muted-foreground text-sm'>
                    Meridinate
                  </span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
