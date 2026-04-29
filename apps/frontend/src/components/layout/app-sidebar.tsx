'use client';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger
} from '@/components/ui/collapsible';
// DropdownMenu removed — no longer needed without Clerk user menu
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
import { navItems } from '@/constants/data';
import { useMediaQuery } from '@/hooks/use-media-query';
import { MasterControlModal } from '@/components/master-control-modal';
import { useApiSettings } from '@/contexts/ApiSettingsContext';
import {
  IconChevronRight,
  IconTags,
  IconAdjustments
} from '@tabler/icons-react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import * as React from 'react';
import { Icons } from '../icons';

interface AppSidebarProps {
  onCodexToggle?: () => void;
  onTagRefToggle?: () => void;
  showTagRef?: boolean;
}

export default function AppSidebar({
  onCodexToggle,
  onTagRefToggle,
  showTagRef = false
}: AppSidebarProps) {
  const pathname = usePathname();
  const { isOpen } = useMediaQuery();
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
            <SidebarMenu>
              {/* Intel Agent — top of sidebar */}
              <SidebarMenuItem key='intel-top'>
                <SidebarMenuButton asChild tooltip='Intel Agent'>
                  <Link href='/dashboard/intel'>
                    <Icons.help className='h-4 w-4' />
                    <span>Intel Agent</span>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
              {/* Bot Probe */}
              <SidebarMenuItem key='bot-probe-top'>
                <SidebarMenuButton asChild tooltip='Bot Probe — Reverse engineer profitable bots'>
                  <Link href='/dashboard/bot-probe'>
                    <Icons.laptop className='h-4 w-4' />
                    <span>Bot Probe</span>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
              {/* Tag Reference */}
              <SidebarMenuItem key='tag-reference-top'>
                <SidebarMenuButton
                  onClick={onTagRefToggle}
                  tooltip='Tag Reference'
                  className={showTagRef ? 'bg-primary/10 text-primary' : ''}
                >
                  <Icons.help className={`h-4 w-4 ${showTagRef ? 'text-primary' : ''}`} />
                  <span>Tag Reference</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
            <div className='my-2 border-b border-muted-foreground/20' />
            <SidebarGroupLabel>Overview</SidebarGroupLabel>
            <SidebarMenu>
              {/* Render nav items with Codex inserted */}
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

                // Insert Codex after Command Center (index 3)
                if (index === 3) {
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
            <SidebarMenuButton size='lg' className='cursor-default'>
              <span className='text-muted-foreground text-sm font-medium'>
                Meridinate
              </span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
