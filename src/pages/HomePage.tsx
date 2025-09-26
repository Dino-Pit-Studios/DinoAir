import { useEffect, useState } from 'react';

import Banner from '../components/common/Banner';
import Button from '../components/common/Button';
import Home from '../components/icons/Home';
import PageContainer from '../components/layout/PageContainer';
import PageHeader from '../components/layout/PageHeader';
import { API_BASE_URL, getHealth } from '../lib/api';

/**
 * HomePage component that displays the home page, including a welcome banner, recent discussion history, and API status.
 * @returns JSX.Element representing the rendered home page.
 */
export default function HomePage() {
  const [history] = useState<{ id: number; title: string }[]>([
    { id: 1, title: 'Project Discussion - Sprint 1' },
    { id: 2, title: 'Weekly Team Meeting Notes' },
    { id: 3, title: 'Brainstorm: New Features' },
  ]);
  const [loading, setLoading] = useState(false);

  const [apiStatus, setApiStatus] = useState<string>('unknown');
  const [apiLoading, setApiLoading] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);

  /**
  /**
  * Checks the API health status by calling getHealth and updates component state accordingly.
  * @returns Promise<void>
  */
  const checkApi = useCallback(async () => {
    setApiLoading(true);
    setApiError(null);
    try {
      const res = await getHealth();
      setApiStatus(res?.status ?? 'ok');
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setApiError(msg);
      setApiStatus('down');
    } finally {
      setApiLoading(false);
    }
  }, []);

  useEffect(() => {
    checkApi();
  }, []);

  const handleStartNewChat = useCallback(() => {
    setLoading(true);
  }, [setLoading]);

  const handleCancel = useCallback(() => {
    setLoading(false);
  }, [setLoading]);

  return (
    <PageContainer className='home-page'>
      <PageHeader icon={<Home width={20} height={20} />} title='Home' />

      <section style={{ marginBottom: 16, display: 'grid', gap: 8 }}>
        <Banner type='info'>Welcome to DinoAir3!</Banner>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ color: '#9ca3af' }}>API:</span>
          <code style={{ color: '#e5e7eb' }}>{API_BASE_URL}</code>

          <span style={{ color: '#9ca3af' }}>Status:</span>
          <strong
            style={{
              color: apiStatus === 'ok' || apiStatus === 'healthy' ? '#34d399' : '#f87171',
            }}
          >
            {apiStatus}
          </strong>

          <Button onClick={checkApi} variant='secondary' disabled={apiLoading}>
            {apiLoading ? 'Checking…' : 'Check API'}
          </Button>

          {apiError ? <span style={{ color: '#fca5a5' }}>{apiError}</span> : null}
        </div>
      </section>

      <section style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 16 }}>
        <div>
          <h2 style={{ marginTop: 0, fontSize: 16, color: '#cdd6ff' }}>Chat History</h2>
          <ul
            style={{
              listStyle: 'none',
              padding: 0,
              margin: 0,
              display: 'grid',
              gap: 8,
            }}
          >
            {history.map(h => (
              <li
                key={h.id}
                style={{
                  background: '#0f3460',
                  border: '1px solid #2a3b7a',
                  padding: '10px 12px',
                  borderRadius: 8,
                  color: '#e6eaff',
                }}
              >
                {h.title}
              </li>
            ))}
          </ul>
        </div>

        <aside>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <Button onClick={handleStartNewChat} variant='primary'>
              Start New Chat
            </Button>
            <Button onClick={handleCancel} variant='secondary'>
              Cancel
            </Button>
            {loading ? (
              <span style={{ color: '#ffffff', fontWeight: 700, fontSize: 14 }}>Loading...</span>
            ) : null}
          </div>
        </aside>
      </section>
    </PageContainer>
  );
}
