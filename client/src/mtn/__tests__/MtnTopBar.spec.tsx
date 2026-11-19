import React from 'react';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';

let mockStartupConfig: Record<string, unknown> = {};
let mockExpanded = false;
const mockSetSidebarOpen = jest.fn();

jest.mock('~/hooks', () => ({ useLocalize: () => (key: string) => key }));
jest.mock('~/data-provider', () => ({
  useGetStartupConfig: () => ({ data: mockStartupConfig }),
}));
jest.mock('~/hooks/AuthContext', () => ({
  useAuthContext: () => ({ user: { name: 'Lerato Dube' } }),
}));
jest.mock('~/hooks/Nav/useSidebarToggle', () => ({
  __esModule: true,
  default: () => ({ setSidebarOpen: mockSetSidebarOpen }),
}));
jest.mock('~/hooks/Nav/useSidebarState', () => ({
  __esModule: true,
  default: () => ({ expanded: mockExpanded }),
}));

import MtnTopBar from '../MtnTopBar';
import { initialsOf, resetMtnAssetManifest } from '../useMtnLayout';

function mockManifest(official: string[] | 'error') {
  global.fetch = jest.fn(() =>
    official === 'error'
      ? Promise.reject(new Error('offline'))
      : Promise.resolve({ ok: true, json: () => Promise.resolve({ official }) }),
  ) as unknown as typeof fetch;
}

describe('MtnTopBar', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    resetMtnAssetManifest();
    mockStartupConfig = { helpAndFaqURL: 'https://help.example.test/faq' };
    mockExpanded = false;
    mockManifest([]);
  });
  afterEach(cleanup);

  it('shows the app name, the static workspace label and the user initials', () => {
    render(<MtnTopBar />);
    expect(screen.getByText('com_mtn_app_name')).toBeInTheDocument();
    expect(screen.getByText('com_mtn_internal_workspace')).toBeInTheDocument();
    expect(screen.getByText('LD')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'com_mtn_home' })).toHaveAttribute('href', '/c/new');
  });

  it('opens HELP_AND_FAQ_URL in a new tab, safely', () => {
    render(<MtnTopBar />);
    const help = screen.getByRole('link', { name: 'com_mtn_help_new_tab' });
    expect(help).toHaveAttribute('href', 'https://help.example.test/faq');
    expect(help).toHaveAttribute('target', '_blank');
    expect(help).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it.each([undefined, '/'])('hides the help button when the URL is %p', (url) => {
    mockStartupConfig = { helpAndFaqURL: url };
    render(<MtnTopBar />);
    expect(screen.queryByTestId('mtn-help')).toBeNull();
  });

  it('has no notifications button', () => {
    render(<MtnTopBar />);
    expect(screen.queryByRole('button', { name: /notification/i })).toBeNull();
  });

  it('toggles the sidebar and reports its state', () => {
    const { unmount } = render(<MtnTopBar />);
    const toggle = screen.getByRole('button', { name: 'com_nav_open_sidebar' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(toggle);
    expect(mockSetSidebarOpen).toHaveBeenCalledWith(true);
    unmount();

    mockExpanded = true;
    render(<MtnTopBar />);
    expect(screen.getByRole('button', { name: 'com_nav_close_sidebar' })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
    fireEvent.click(screen.getByRole('button', { name: 'com_nav_close_sidebar' }));
    expect(mockSetSidebarOpen).toHaveBeenLastCalledWith(false);
  });

  it('uses the cropped fallback logo until an official logo is published', async () => {
    const { container } = render(<MtnTopBar />);
    await waitFor(() => expect(global.fetch).toHaveBeenCalled());
    expect(container.querySelector('.mtn-logo img')).toHaveAttribute('src', '/assets/logo.svg');
  });

  it('switches to the official logo SVG when the branding image publishes one', async () => {
    mockManifest(['logo/logo']);
    const { container } = render(<MtnTopBar />);
    await waitFor(() =>
      expect(container.querySelector('.mtn-logo img')).toHaveAttribute(
        'src',
        '/assets/mtn/logo/logo.svg',
      ),
    );
  });

  it('keeps the fallback logo when the manifest cannot be loaded', async () => {
    mockManifest('error');
    const { container } = render(<MtnTopBar />);
    await waitFor(() => expect(global.fetch).toHaveBeenCalled());
    expect(container.querySelector('.mtn-logo img')).toHaveAttribute('src', '/assets/logo.svg');
  });
});

describe('initialsOf', () => {
  it.each([
    ['Lerato Dube', 'LD'],
    ['  thabo  ', 'T'],
    ['Ama Kofi Mensah', 'AM'],
    ['', ''],
    [undefined, ''],
  ])('%p -> %p', (name, expected) => {
    expect(initialsOf(name)).toBe(expected);
  });
});
