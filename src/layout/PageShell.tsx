// no React default import needed with react-jsx

import { Outlet } from 'react-router-dom';

import FooterLinks from '../components/common/FooterLinks';
import SidebarNav from '../components/nav/SidebarNav';
import TopNav from '../components/nav/TopNav';

/**
 * PageShell - Layout component wrapping the application shell including header, sidebar, main content, and footer.
 *
 * @returns {JSX.Element} The page layout element.
 */
export default function PageShell() {
  return (
    <div
      className='app-root'
      style={{
        background: '#0b0f17',
        minHeight: '100vh',
        color: '#e5e7eb',
        display: 'flex',
        flexDirection: 'column',
        WebkitFontSmoothing: 'antialiased',
        MozOsxFontSmoothing: 'grayscale',
      }}
    >
      <header className='topnav' style={{ padding: 0 }}>
        <TopNav />
      </header>

      <div style={{ display: 'flex', gap: 16, padding: 0, flex: 1 }}>
        {/* Optional sidebar placeholder — hidden for now */}
        <aside aria-label='Sidebar navigation' style={{ display: 'none' }}>
          <SidebarNav />
        </aside>

        <main className='content' style={{ flex: 1, minWidth: 0 }}>
          <div style={{ maxWidth: 1200, margin: '0 auto', padding: 24 }}>
            <Outlet />
          </div>
        </main>
      </div>

      <footer
        className='footer'
        style={{
          borderTop: '1px solid #1f2937',
          padding: 16,
          color: '#9ca3af',
        }}
      >
        <FooterLinks />
      </footer>
    </div>
  );
}
