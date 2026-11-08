/**
 * MTN fork: the yellow MTN top bar (black with a yellow rule in dark mode). Rendered by Root only
 * when `interface.mtnLayout` is on.
 */
import { memo, useCallback } from 'react';
import { Menu, CircleHelp } from 'lucide-react';
import { initialsOf, useMtnOfficialAsset } from './useMtnLayout';
import useSidebarToggle from '~/hooks/Nav/useSidebarToggle';
import useSidebarState from '~/hooks/Nav/useSidebarState';
import { useGetStartupConfig } from '~/data-provider';
import { useAuthContext } from '~/hooks/AuthContext';
import { useLocalize } from '~/hooks';
import './mtn-layout.css';

export const MTN_SIDEBAR_ID = 'mtn-sidebar';

function MtnTopBar() {
  const localize = useLocalize();
  const { user } = useAuthContext();
  const { data: startupConfig } = useGetStartupConfig();
  const { expanded } = useSidebarState();
  const { setSidebarOpen } = useSidebarToggle();
  const officialLogo = useMtnOfficialAsset('logo/logo');

  const helpUrl = startupConfig?.helpAndFaqURL;
  const showHelp = !!helpUrl && helpUrl !== '/';
  const name = user?.name ?? user?.username ?? '';

  const toggleSidebar = useCallback(() => setSidebarOpen(!expanded), [expanded, setSidebarOpen]);

  return (
    <header className="mtn-topbar" data-testid="mtn-topbar">
      <button
        type="button"
        className="mtn-topbar-btn"
        aria-label={localize(expanded ? 'com_nav_close_sidebar' : 'com_nav_open_sidebar')}
        aria-expanded={expanded}
        aria-controls={MTN_SIDEBAR_ID}
        onClick={toggleSidebar}
      >
        <Menu className="h-5 w-5" aria-hidden="true" />
      </button>
      <a href="/c/new" className="mtn-brand" aria-label={localize('com_mtn_home')}>
        <span className={officialLogo ? 'mtn-logo mtn-logo-official' : 'mtn-logo'}>
          <img
            src={officialLogo ? '/assets/mtn/logo/logo.svg' : '/assets/logo.svg'}
            alt=""
            draggable={false}
          />
        </span>
        <span className="mtn-wordmark">{localize('com_mtn_app_name')}</span>
      </a>
      <span className="flex-1" />
      <span className="mtn-workspace hidden md:inline">
        {localize('com_mtn_internal_workspace')}
      </span>
      {showHelp && (
        <a
          className="mtn-topbar-btn"
          href={helpUrl}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={localize('com_mtn_help_new_tab')}
          data-testid="mtn-help"
        >
          <CircleHelp className="h-5 w-5" aria-hidden="true" />
        </a>
      )}
      {name && (
        <span className="mtn-avatar" title={name} aria-hidden="true">
          {initialsOf(name)}
        </span>
      )}
    </header>
  );
}

export default memo(MtnTopBar);
