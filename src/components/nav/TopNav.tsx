import { useState, type CSSProperties, type ComponentType, type SVGProps } from 'react';
import { NavLink } from 'react-router-dom';

import ArtifactsPage from '../icons/ArtifactsPage';
import Chat from '../icons/Chat';
import Home from '../icons/Home';
import LocalFileRetrievalAndIndexing from '../icons/LocalFileRetrievalAndIndexing';
import ModelSettingsSystemWatchdog from '../icons/ModelSettingsSystemWatchdog';
import Notes from '../icons/Notes';
import OtherToolsPage from '../icons/OtherToolsPage';
import Projects from '../icons/Projects';
import SettingsPage from '../icons/SettingsPage';

type Item = {
  to: string;
  label: string;
  Icon: ComponentType<SVGProps<SVGSVGElement>>;
};

const items: Item[] = [
  { to: '/', label: 'Home', Icon: Home },
  { to: '/chat', label: 'Chat', Icon: Chat },
  { to: '/projects', label: 'Projects', Icon: Projects },
  { to: '/artifacts', label: 'Artifacts', Icon: ArtifactsPage },
  { to: '/notes', label: 'Notes', Icon: Notes },
  { to: '/tools', label: 'Tools', Icon: OtherToolsPage },
  { to: '/utilities', label: 'Utilities', Icon: OtherToolsPage },
  { to: '/files', label: 'Files', Icon: LocalFileRetrievalAndIndexing },
  { to: '/model-settings', label: 'Model', Icon: ModelSettingsSystemWatchdog },
  { to: '/settings', label: 'Settings', Icon: SettingsPage },
];

const tokens = {
  textBase: '#a3a3a3',
  textHover: '#e5e7eb',
  textActive: '#60a5fa',
  headerBg: '#111827',
  border: '#1f2937',
  focusRing: '#374151',
} as const;

/**
 * Renders a navigation link item with an icon and label.
 *
 * @param {string} to - The destination path for the navigation link.
 * @param {string} label - The text label displayed for the link.
 * @param {React.ComponentType<{ width?: number; height?: number }>} Icon - The icon component to render alongside the label.
 * @returns {JSX.Element} The rendered navigation link item.
 */
function LinkItem({ to, label, Icon }: Item) {
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);

  const handleMouseEnter = React.useCallback(() => setHovered(true), []);
  const handleMouseLeave = React.useCallback(() => setHovered(false), []);
  const handleFocus = React.useCallback(() => setFocused(true), []);
  const handleBlur = React.useCallback(() => setFocused(false), []);
  const linkClassName = React.useCallback(
    ({ isActive }: { isActive: boolean }) => `nav-link${isActive ? ' is-active' : ''}`,
    []
  );
  const linkStyle = React.useCallback(
    ({ isActive }: { isActive: boolean }) => {
      const color = isActive ? tokens.textActive : hovered ? tokens.textHover : tokens.textBase;
      return {
        color,
        borderBottom: isActive ? `2px solid ${tokens.textActive}` : '2px solid transparent',
        textDecoration: 'none',
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '0 8px',
        height: 56,
        outline: focused ? `2px solid ${tokens.focusRing}` : 'none',
        outlineOffset: 2,
      } as CSSProperties;
    },
    [hovered, focused]
  );

  return (
    <NavLink
      key={to}
      to={to}
      className={linkClassName}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onFocus={handleFocus}
      onBlur={handleBlur}
      style={linkStyle}
    >
      <Icon width={16} height={16} />
      <span>{label}</span>
    </NavLink>
  );
}

/**
 * TopNav renders the top navigation bar for the application.
 *
 * @returns {JSX.Element} The navigation bar component.
 */
export default function TopNav() {
  return (
    <div
      style={{
        width: '100%',
        background: tokens.headerBg,
        borderBottom: `1px solid ${tokens.border}`,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          height: 56,
          padding: '0 18px',
        }}
      >
        <h1 style={{ margin: 0, fontSize: 18, color: tokens.textHover }}>DinoAir3</h1>
        <nav aria-label='Primary' style={{ display: 'flex', gap: 18, alignItems: 'center' }}>
          {items.map(it => (
            <LinkItem key={it.to} {...it} />
          ))}
        </nav>
      </div>
    </div>
  );
}
