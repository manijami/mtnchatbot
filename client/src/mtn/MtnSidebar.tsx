/**
 * MTN fork: the MTN sidebar (dark in both modes): New chat, navigation (Chats, Projects,
 * Assistants, My files, More tools), upstream's chat list panel, and a user card.
 * Rendered by UnifiedSidebar in place of the icon rail when `interface.mtnLayout` is on.
 * Upstream behaviour is reused: the chat list, search, panels and account menu are the
 * upstream components; only the frame around them is MTN's.
 */
import { memo, useCallback, useMemo, useState, Suspense } from 'react';
import { useSetAtom } from 'jotai';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  Plus,
  Folder,
  Settings,
  Sparkles,
  FileText,
  ChevronDown,
  LayoutGrid,
  MessageSquare,
} from 'lucide-react';
import type { TModelSpec, TEndpointsConfig } from 'librechat-data-provider';
import type { NavLink } from '~/common';
import {
  DRAWER_Z_INDEX,
  MOBILE_DRAWER_ID,
  MOBILE_DRAWER_WIDTH,
} from '~/components/UnifiedSidebar/constants';
import { useActivePanel, useAssistantsMapContext, DEFAULT_PANEL } from '~/Providers';
import { useGetEndpointsQuery, useGetStartupConfig } from '~/data-provider';
import { useGetConversation, useLocalize, useNewConvo } from '~/hooks';
import useSelectMention from '~/hooks/Input/useSelectMention';
import { settingsOpenAtom } from '~/components/Nav/Settings';
import { showFilesDialogAtom } from '~/store/filesDialog';
import useNewChat from '~/hooks/Conversations/useNewChat';
import SidePanelNav from '~/components/SidePanel/Nav';
import { lazyWithRecovery } from '~/lib/assets/lazy';
import { MTN_SIDEBAR_ID } from './MtnTopBar';
import { cn } from '~/utils';
import './mtn-layout.css';

const AccountSettings = lazyWithRecovery(() => import('~/components/Nav/AccountSettings'));

/** Desktop sidebar width (px). */
export const MTN_SIDEBAR_WIDTH = 288;

type NavProps = {
  links: NavLink[];
  switchToHistory: boolean;
  /** Called after any navigation (closes the drawer on phones). */
  onNavigate: () => void;
};

export function MtnSidebarNav({ links, switchToHistory, onNavigate }: NavProps) {
  const localize = useLocalize();
  const location = useLocation();
  const navigate = useNavigate();
  const { active, setActive } = useActivePanel();
  const setShowFiles = useSetAtom(showFilesDialogAtom);
  const [assistantsOpen, setAssistantsOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);

  const { data: startupConfig } = useGetStartupConfig();
  const { data: endpointsConfig = {} as TEndpointsConfig } = useGetEndpointsQuery();
  const assistantsMap = useAssistantsMapContext();
  const getConversation = useGetConversation(0);
  const { newConversation } = useNewConvo();
  const specs = useMemo(
    () => startupConfig?.modelSpecs?.list ?? [],
    [startupConfig?.modelSpecs?.list],
  );
  const { onSelectSpec } = useSelectMention({
    modelSpecs: specs,
    assistantsMap,
    endpointsConfig,
    getConversation,
    newConversation,
    returnHandlers: true,
  });

  const onProjects = location.pathname.startsWith('/projects');
  const chatsActive = !onProjects && (active ?? DEFAULT_PANEL) === DEFAULT_PANEL;
  const otherLinks = useMemo(() => links.filter((link) => link.id !== DEFAULT_PANEL), [links]);

  const handlePanelSwitch = useCallback(() => {
    if (switchToHistory) {
      setActive(DEFAULT_PANEL);
    }
    onNavigate();
  }, [switchToHistory, setActive, onNavigate]);
  const { handleNewChatClick } = useNewChat({ onNewChat: handlePanelSwitch });

  const openChats = useCallback(() => {
    setActive(DEFAULT_PANEL);
    if (onProjects) {
      navigate('/c/new');
      onNavigate();
    }
  }, [setActive, onProjects, navigate, onNavigate]);

  const openProjects = useCallback(() => {
    navigate('/projects');
    onNavigate();
  }, [navigate, onNavigate]);

  const openFiles = useCallback(() => setShowFiles(true), [setShowFiles]);

  const selectSpec = useCallback(
    (spec: TModelSpec) => {
      onSelectSpec?.(spec);
      setActive(DEFAULT_PANEL);
      onNavigate();
    },
    [onSelectSpec, setActive, onNavigate],
  );

  const openLink = useCallback(
    (link: NavLink, event: React.MouseEvent<HTMLButtonElement>) => {
      if (link.onClick) {
        link.onClick(event);
        onNavigate();
        return;
      }
      setActive(link.id);
    },
    [setActive, onNavigate],
  );

  return (
    <div className="flex shrink-0 flex-col gap-1 px-3 pt-4 pb-2">
      <a
        href="/c/new"
        className="mtn-newchat"
        data-testid="mtn-new-chat"
        onClick={handleNewChatClick}
      >
        <Plus className="h-5 w-5" aria-hidden="true" />
        {localize('com_ui_new_chat')}
      </a>
      <nav aria-label={localize('com_mtn_main_navigation')} className="mt-3 flex flex-col gap-0.5">
        <button
          type="button"
          className="mtn-nav-item"
          aria-current={chatsActive ? 'page' : undefined}
          onClick={openChats}
        >
          <MessageSquare className="h-5 w-5" aria-hidden="true" />
          {localize('com_ui_chats')}
        </button>
        <button
          type="button"
          className="mtn-nav-item"
          aria-current={onProjects ? 'page' : undefined}
          onClick={openProjects}
        >
          <Folder className="h-5 w-5" aria-hidden="true" />
          {localize('com_ui_projects')}
        </button>
        {specs.length > 0 && (
          <>
            <button
              type="button"
              className="mtn-nav-item"
              aria-expanded={assistantsOpen}
              aria-controls="mtn-assistants-list"
              onClick={() => setAssistantsOpen((open) => !open)}
            >
              <Sparkles className="h-5 w-5" aria-hidden="true" />
              <span className="flex-1">{localize('com_ui_assistants')}</span>
              <ChevronDown
                className={cn('h-4 w-4 transition-transform', assistantsOpen && 'rotate-180')}
                aria-hidden="true"
              />
            </button>
            <ul id="mtn-assistants-list" hidden={!assistantsOpen} className="flex flex-col">
              {specs.map((spec) => (
                <li key={spec.name}>
                  <button
                    type="button"
                    className="mtn-subitem"
                    aria-label={localize('com_mtn_start_chat_with', { 0: spec.label })}
                    onClick={() => selectSpec(spec)}
                  >
                    {spec.iconURL?.startsWith('/') && <img src={spec.iconURL} alt="" />}
                    <span className="min-w-0">
                      {spec.label}
                      {spec.description && <small>{spec.description}</small>}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
        <button type="button" className="mtn-nav-item" onClick={openFiles}>
          <FileText className="h-5 w-5" aria-hidden="true" />
          {localize('com_nav_my_files')}
        </button>
        {otherLinks.length > 0 && (
          <>
            <button
              type="button"
              className="mtn-nav-item"
              aria-expanded={moreOpen}
              aria-controls="mtn-more-list"
              onClick={() => setMoreOpen((open) => !open)}
            >
              <LayoutGrid className="h-5 w-5" aria-hidden="true" />
              <span className="flex-1">{localize('com_mtn_more_tools')}</span>
              <ChevronDown
                className={cn('h-4 w-4 transition-transform', moreOpen && 'rotate-180')}
                aria-hidden="true"
              />
            </button>
            <ul id="mtn-more-list" hidden={!moreOpen} className="flex flex-col">
              {otherLinks.map((link) => (
                <li key={link.id}>
                  <button
                    type="button"
                    className="mtn-subitem"
                    aria-current={active === link.id ? 'page' : undefined}
                    disabled={link.disabled}
                    onClick={(event) => openLink(link, event)}
                  >
                    <link.icon className="h-4 w-4" aria-hidden="true" />
                    {localize(link.title)}
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </nav>
    </div>
  );
}

function MtnUserCard() {
  const localize = useLocalize();
  const setShowSettings = useSetAtom(settingsOpenAtom);
  return (
    <div className="mtn-sidebar-divider flex shrink-0 items-center gap-1 px-3 py-3">
      <div className="min-w-0 flex-1">
        <Suspense fallback={<div className="h-12" />}>
          <AccountSettings subtitle={localize('com_mtn_role_employee')} />
        </Suspense>
      </div>
      <button
        type="button"
        className="mtn-topbar-btn mtn-card-btn shrink-0"
        aria-label={localize('com_nav_settings')}
        onClick={() => setShowSettings(true)}
      >
        <Settings className="h-5 w-5" aria-hidden="true" />
      </button>
    </div>
  );
}

function MtnSidebarContent({ links, switchToHistory, onNavigate }: NavProps) {
  return (
    <div id={MTN_SIDEBAR_ID} className="flex h-full min-h-0 flex-col">
      <MtnSidebarNav links={links} switchToHistory={switchToHistory} onNavigate={onNavigate} />
      <div className="mtn-sidebar-divider mx-3" />
      <nav id="chat-history-nav" className="min-h-0 flex-1 overflow-hidden">
        <SidePanelNav links={links} />
      </nav>
      <MtnUserCard />
    </div>
  );
}

export type MtnSidebarProps = NavProps & {
  isSmallScreen: boolean;
  expanded: boolean;
  isSliding: boolean;
};

function MtnSidebar({
  links,
  expanded,
  isSliding,
  isSmallScreen,
  switchToHistory,
  onNavigate,
}: MtnSidebarProps) {
  const localize = useLocalize();
  if (isSmallScreen) {
    return (
      <div
        id={MOBILE_DRAWER_ID}
        data-testid="mtn-sidebar"
        data-unpainted={expanded || isSliding ? undefined : ''}
        className={cn(
          'mtn-sidebar mtn-drawer dark absolute inset-y-0 inset-s-0 flex touch-pan-y flex-col',
          expanded ? 'translate-x-0' : '-translate-x-full rtl:translate-x-full',
        )}
        style={{ width: MOBILE_DRAWER_WIDTH, zIndex: DRAWER_Z_INDEX }}
        inert={!expanded ? '' : undefined}
      >
        <MtnSidebarContent
          links={links}
          switchToHistory={switchToHistory}
          onNavigate={onNavigate}
        />
      </div>
    );
  }
  return (
    <aside
      data-testid="mtn-sidebar"
      aria-label={localize('com_nav_control_panel')}
      className="mtn-sidebar mtn-sidebar-desktop dark relative h-full shrink-0 overflow-hidden"
      style={{ width: expanded ? MTN_SIDEBAR_WIDTH : 0 }}
      inert={!expanded ? '' : undefined}
    >
      <div className="h-full" style={{ width: MTN_SIDEBAR_WIDTH }}>
        <MtnSidebarContent
          links={links}
          switchToHistory={switchToHistory}
          onNavigate={onNavigate}
        />
      </div>
    </aside>
  );
}

export default memo(MtnSidebar);
