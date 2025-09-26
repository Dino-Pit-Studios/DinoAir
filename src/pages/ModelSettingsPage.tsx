import { useMemo, useState, useCallback, type CSSProperties, type ChangeEvent } from 'react';

import Card from '../components/common/Card';
import MetricTile from '../components/common/MetricTile';
import Toggle from '../components/common/Toggle';
import ModelSettingsSystemWatchdog from '../components/icons/ModelSettingsSystemWatchdog';
import PageContainer from '../components/layout/PageContainer';
import PageHeader from '../components/layout/PageHeader';

/**
 * Renders the Model Settings & System Watchdog page, allowing users to select a preferred model
 * and enable or disable the system watchdog. Displays connection status and relevant metrics.
 *
 * @returns JSX.Element The rendered ModelSettingsPage component.
 */
export default function ModelSettingsPage() {
  const [model, setModel] = useState('gpt-4o-mini');
  const [watchdogOn, setWatchdogOn] = useState(true);

  const connectionOk = true;

  const statusDot: CSSProperties = useMemo(
    () => ({
      display: 'inline-block',
      width: 10,
      height: 10,
      borderRadius: 5,
      background: connectionOk ? '#32bc9b' : '#7a2a2f',
      marginRight: 6,
    }),
    [connectionOk]
  );

  const handleModelChange = useCallback((e: ChangeEvent<HTMLSelectElement>) => {
    setModel(e.target.value);
  }, []);

  return (
    <PageContainer className='model-settings-page'>
      <PageHeader
        icon={<ModelSettingsSystemWatchdog width={20} height={20} />}
        title='Model Settings & System Watchdog'
      />

      <section style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <Card title='Model Settings'>
          <div style={{ display: 'grid', gap: 10 }}>
            <label style={{ display: 'grid', gap: 6 }}>
              <span style={{ color: '#cdd6ff', fontSize: 14 }}>Preferred Model</span>
              <select
                value={model}
                onChange={handleModelChange}
                style={{
                  background: '#0f3460',
                  border: '1px solid #2a3b7a',
                  color: '#e6eaff',
                  borderRadius: 6,
                  padding: '8px 10px',
                  fontSize: 14,
                }}
              >
                <option value='gpt-4o-mini'>gpt-4o-mini</option>
                <option value='gpt-4.1'>gpt-4.1</option>
                <option value='llama-3.1-70b'>llama-3.1-70b</option>
              </select>
            </label>

            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={statusDot} />
              <span style={{ color: '#aef2de', fontSize: 13 }}>
                {connectionOk ? 'Connected' : 'Disconnected'}
              </span>
            </div>
          </div>
        </Card>

        <Card title='System & Process Watchdog'>
          <div style={{ display: 'grid', gap: 12 }}>
            <Toggle checked={watchdogOn} onChange={setWatchdogOn} label='Enable Watchdog' />

            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <MetricTile label='CPU' value='23%' />
              <MetricTile label='Memory' value='3.1 GB' />
              <MetricTile label='Queue' value={watchdogOn ? 'OK' : 'Paused'} />
            </div>
          </div>
        </Card>
      </section>
    </PageContainer>
  );
}
