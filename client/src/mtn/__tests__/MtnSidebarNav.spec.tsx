import React from 'react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import type { NavLink } from '~/common';

const mockSetActive = jest.fn();
const mockOnSelectSpec = jest.fn();
const mockHandleNewChatClick = jest.fn();
let mockActive = 'conversations';

jest.mock('~/hooks', () => ({
  useLocalize: () => (key: string, values?: Record<string, string>) =>
    values ? `${key}:${values[0]}` : key,
  useGetConversation: () => () => null,
  useNewConvo: () => ({ newConversation: jest.fn() }),
}));
jest.mock('~/Providers', () => ({
  useActivePanel: () => ({ active: mockActive, setActive: mockSetActive }),
  useAssistantsMapContext: () => ({}),
  DEFAULT_PANEL: 'conversations',
}));
jest.mock('~/data-provider', () => ({
  useGetEndpointsQuery: () => ({ data: {} }),
  useGetStartupConfig: () => ({
    data: {
      modelSpecs: {
        list: [
          {
            name: 'mtn-document-assistant',
            label: 'MTN Document Assistant',
            description: 'Creates MTN-branded files.',
            iconURL: '/assets/mtn/avatars/document-assistant.svg',
            preset: { endpoint: 'nvidia' },
          },
          {
            name: 'mtn-smart-chat',
            label: 'MTN Smart Chat',
            iconURL: '/assets/mtn/avatars/smart-chat.svg',
            preset: { endpoint: 'MTN Smart Router' },
          },
        ],
      },
    },
  }),
}));
jest.mock('~/hooks/Input/useSelectMention', () => ({
  __esModule: true,
  default: () => ({ onSelectSpec: mockOnSelectSpec }),
}));
jest.mock('~/hooks/Conversations/useNewChat', () => ({
  __esModule: true,
  default: () => ({ handleNewChatClick: mockHandleNewChatClick }),
}));
jest.mock('~/components/Nav/Settings', () => ({ settingsOpenAtom: {} }));
jest.mock('~/components/SidePanel/Nav', () => ({ __esModule: true, default: () => null }));
jest.mock('~/lib/assets/lazy', () => ({ lazyWithRecovery: () => () => null }));

import { MtnSidebarNav } from '../MtnSidebar';

const Icon = () => <svg />;
const links: NavLink[] = [
  { id: 'conversations', title: 'com_ui_chat_history', label: '', icon: Icon },
  { id: 'prompts', title: 'com_ui_prompts', label: '', icon: Icon },
  { id: 'bookmarks', title: 'com_sidepanel_conversation_tags', label: '', icon: Icon },
] as unknown as NavLink[];

function WhereAmI() {
  return <output data-testid="path">{useLocation().pathname}</output>;
}

function renderNav(path = '/c/new', onNavigate = jest.fn()) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="*"
          element={
            <>
              <MtnSidebarNav links={links} switchToHistory={false} onNavigate={onNavigate} />
              <WhereAmI />
            </>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
  return onNavigate;
}

describe('MtnSidebarNav', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockActive = 'conversations';
  });
  afterEach(cleanup);

  it('renders New chat and the main navigation with Chats as the current page', () => {
    renderNav();
    expect(screen.getByTestId('mtn-new-chat')).toHaveAttribute('href', '/c/new');
    const nav = screen.getByRole('navigation', { name: 'com_mtn_main_navigation' });
    expect(nav).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'com_ui_chats' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    for (const name of ['com_ui_projects', 'com_ui_assistants', 'com_nav_my_files']) {
      expect(screen.getByRole('button', { name })).toBeInTheDocument();
    }
  });

  it('starts a new chat through the upstream new-chat handler', () => {
    renderNav();
    fireEvent.click(screen.getByTestId('mtn-new-chat'));
    expect(mockHandleNewChatClick).toHaveBeenCalled();
  });

  it('opens Projects and marks it current on the projects route', () => {
    const onNavigate = renderNav();
    fireEvent.click(screen.getByRole('button', { name: 'com_ui_projects' }));
    expect(screen.getByTestId('path')).toHaveTextContent('/projects');
    expect(onNavigate).toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'com_ui_projects' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(screen.getByRole('button', { name: 'com_ui_chats' })).not.toHaveAttribute(
      'aria-current',
    );
  });

  it('lists the MTN assistants (model specs) and starts a chat with the chosen one', () => {
    const onNavigate = renderNav();
    const toggle = screen.getByRole('button', { name: 'com_ui_assistants' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(document.getElementById('mtn-assistants-list')).not.toBeVisible();

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    const doc = screen.getByRole('button', {
      name: 'com_mtn_start_chat_with:MTN Document Assistant',
    });
    expect(doc).toHaveTextContent('Creates MTN-branded files.');
    fireEvent.click(doc);
    expect(mockOnSelectSpec).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'mtn-document-assistant' }),
    );
    expect(mockSetActive).toHaveBeenCalledWith('conversations');
    expect(onNavigate).toHaveBeenCalled();
  });

  it('keeps every other upstream panel reachable under More tools', () => {
    renderNav();
    fireEvent.click(screen.getByRole('button', { name: 'com_mtn_more_tools' }));
    expect(screen.queryByRole('button', { name: 'com_ui_chat_history' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'com_ui_prompts' }));
    expect(mockSetActive).toHaveBeenCalledWith('prompts');
  });

  it('does not offer the agents marketplace', () => {
    renderNav();
    expect(screen.queryByText(/marketplace/i)).toBeNull();
  });
});
