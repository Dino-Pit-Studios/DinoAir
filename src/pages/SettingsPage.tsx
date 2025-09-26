import { useCallback, useEffect, useState, type ChangeEvent } from 'react';

import { LiveRegion } from '../components/accessibility/LiveRegion';
import Banner from '../components/common/Banner';
import Button from '../components/common/Button';
import Card from '../components/common/Card';
import Checkbox from '../components/common/Checkbox';
import Toggle from '../components/common/Toggle';
import SettingsIcon from '../components/icons/SettingsPage';
import PageContainer from '../components/layout/PageContainer';
import PageHeader from '../components/layout/PageHeader';
import { useAnnouncement } from '../hooks/useAnnouncement';
import { useResponsive } from '../hooks/useResponsive';
import { API_BASE_URL, getCapabilities, getConfigDirs, getMetrics, getVersion } from '../lib/api';

type VersionInfo = { version?: string; build?: string; commit?: string };
type CapabilitiesResponse = { capabilities?: string[] };
type MetricsResponse = { metrics?: { uptimeSeconds?: number } };
type LMStudioStatus = 'connected' | 'disconnected' | 'unknown';

type BackendIntegrationDetailsProps = Readonly<{
  apiBaseUrl: string;
  versionInfo: VersionInfo | null;
  uptimeSeconds: number;
  capabilities: string[];
  onRefresh: () => void;
  loading: boolean;
  error?: string | null;
}>;

/**
 * Displays details about the backend integration including API base URL, version info, uptime, capabilities, and a refresh action.
 * @param {object} props - The component props.
 * @param {string} props.apiBaseUrl - The base URL for the API.
 * @param {VersionInfo | undefined} props.versionInfo - Information about the backend version.
 * @param {number} props.uptimeSeconds - The uptime of the backend in seconds.
 * @param {any[]} props.capabilities - List of backend capabilities.
 * @param {() => void} props.onRefresh - Callback to refresh the backend information.
 * @param {boolean} props.loading - Whether the data is currently loading.
 * @param {string | null} props.error - Error message if loading fails.
 * @returns {JSX.Element} The rendered component.
 */
function BackendIntegrationDetails({
  apiBaseUrl,
  versionInfo,
  uptimeSeconds,
  capabilities,
  onRefresh,
  loading,
  error,
}: BackendIntegrationDetailsProps) {
  return (
    <div style={{ display: 'grid', gap: 8 }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <span style={{ color: '#9ca3af' }}>API Base:</span>
        <code>{apiBaseUrl}</code>
      </div>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <div>
          Version: <strong>{versionInfo?.version ?? '—'}</strong>
        </div>
        <div>
          Build: <code>{versionInfo?.build ?? '—'}</code>
        </div>
        <div>
          Commit: <code>{versionInfo?.commit ?? '—'}</code>
        </div>
        <div>
          Uptime: <strong>{uptimeSeconds}s</strong>
        </div>
        <div>
          Capabilities: <strong>{capabilities.length}</strong>
        </div>
      </div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <Button
          variant='secondary'
          onClick={onRefresh}
          disabled={loading}
          data-testid='refresh-backend-button'
          aria-label='Refresh backend information'
        >
          {loading ? 'Refreshing…' : 'Refresh Backend Info'}
        </Button>
        {error ? <span style={{ color: '#fca5a5' }}>{error}</span> : null}
      </div>
    </div>
  );
}

type LMStudioConfigProps = Readonly<{
  url: string;
  onUrlChange: (event: ChangeEvent<HTMLInputElement>) => void;
  model: string;
  onModelChange: (event: ChangeEvent<HTMLInputElement>) => void;
  enabled: boolean;
  onEnabledChange: (value: boolean) => void;
  testing: boolean;
  status: LMStudioStatus;
  onTestConnection: () => void;
}>;

/**
 * LMStudioConfig component renders configuration UI for LM Studio integration.
 * @param {string} url - The URL of the LM Studio instance.
 * @param {(e: React.ChangeEvent<HTMLInputElement>) => void} onUrlChange - Handler for URL input changes.
 * @param {string} model - The selected model name.
 * @param {(e: React.ChangeEvent<HTMLInputElement>) => void} onModelChange - Handler for model input changes.
 * @param {boolean} enabled - Whether LM Studio integration is enabled.
 * @param {(checked: boolean) => void} onEnabledChange - Handler for toggling integration enable state.
 * @param {boolean} testing - Whether the connection test is in progress.
 * @param {LMStudioStatus} status - The current connection status.
 * @param {() => void} onTestConnection - Handler to test the LM Studio connection.
 * @returns {JSX.Element} The rendered LM Studio configuration component.
 */
function LMStudioConfig({
  url,
  onUrlChange,
  model,
  onModelChange,
  enabled,
  onEnabledChange,
  testing,
  status,
  onTestConnection,
}: LMStudioConfigProps) {
  const statusStyles: Record<LMStudioStatus, { backgroundColor: string; label: string }> = {
    connected: { backgroundColor: '#059669', label: '● Connected' },
    disconnected: { backgroundColor: '#dc2626', label: '● Disconnected' },
    unknown: { backgroundColor: '#6b7280', label: '● Unknown' },
  };

  const statusStyle = statusStyles[status];

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <div>
        <label htmlFor='lmstudio-url' style={{ display: 'block', marginBottom: 4 }}>
          LM Studio URL:
        </label>
        <input
          id='lmstudio-url'
          type='text'
          value={url}
          onChange={onUrlChange}
          placeholder='http://127.0.0.1:1234'
          style={{
            width: '100%',
            padding: '8px 12px',
            border: '1px solid #374151',
            borderRadius: '4px',
            backgroundColor: '#1f2937',
            color: '#f9fafb',
          }}
        />
      </div>

      <div>
        <label htmlFor='lmstudio-model' style={{ display: 'block', marginBottom: 4 }}>
          Model Name:
        </label>
        <input
          id='lmstudio-model'
          type='text'
          value={model}
          onChange={onModelChange}
          placeholder='llama-3.1-8b-instruct'
          style={{
            width: '100%',
            padding: '8px 12px',
            border: '1px solid #374151',
            borderRadius: '4px',
            backgroundColor: '#1f2937',
            color: '#f9fafb',
          }}
        />
      </div>

      <Toggle checked={enabled} onChange={onEnabledChange} label='Enable LM Studio Integration' />
      <p style={{ fontSize: '0.875rem', color: '#9ca3af', marginTop: '-8px' }}>
        Connect to a local LM Studio instance to power AI responses.
      </p>

      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <Button
          variant='secondary'
          onClick={onTestConnection}
          disabled={testing}
          data-testid='test-lmstudio-button'
        >
          {testing ? 'Testing…' : 'Test Connection'}
        </Button>
        <span
          style={{
            padding: '4px 8px',
            borderRadius: '4px',
            backgroundColor: statusStyle.backgroundColor,
            color: '#fff',
            fontSize: '0.875rem',
          }}
        >
          {statusStyle.label}
        </span>
      </div>
    </div>
  );
}

/**
 * SettingsPage component renders the settings page allowing users to configure
 * general, advanced, and LM Studio settings.
 *
 * @returns JSX.Element - The settings page UI.
 */
export default function SettingsPage() {
  const { isMobile } = useResponsive();
  const { announceSuccess, announceError, announceInfo } = useAnnouncement();

  // General Settings
  const [darkMode, setDarkMode] = useState(true);
  const [notifications, setNotifications] = useState(true);
  const [autoSave, setAutoSave] = useState(false);

  // Advanced Settings
  const [advancedEnabled, setAdvancedEnabled] = useState(false);
  const [betaFeatures, setBetaFeatures] = useState(false);
  const [telemetry, setTelemetry] = useState(true);

  // Save state
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  // Backend integration
  const [backendLoading, setBackendLoading] = useState(false);
  const [backendError, setBackendError] = useState<string | null>(null);
  const [ver, setVer] = useState<VersionInfo | null>(null);
  const [caps, setCaps] = useState<string[]>([]);
  const [uptimeSeconds, setUptimeSeconds] = useState<number>(0);

  // LM Studio Settings
  const [lmStudioUrl, setLmStudioUrl] = useState('http://127.0.0.1:1234');
  const [lmStudioModel, setLmStudioModel] = useState('llama-3.1-8b-instruct');
  const [lmStudioEnabled, setLmStudioEnabled] = useState(true);
  const [lmStudioTesting, setLmStudioTesting] = useState(false);
  const [lmStudioStatus, setLmStudioStatus] = useState<LMStudioStatus>('unknown');

  const loadBackendInfo = useCallback(async () => {
    setBackendLoading(true);
    setBackendError(null);
    announceInfo('Loading backend information...');
    try {
      const [versionResponse, capabilitiesResponse, metricsResponse] = await Promise.all([
        getVersion(),
        getCapabilities(),
        getMetrics(),
      ]);
      await getConfigDirs();

      const versionInfo = (versionResponse as VersionInfo | undefined) ?? null;
      const capsPayload = capabilitiesResponse as CapabilitiesResponse | undefined;
      const metricsPayload = metricsResponse as MetricsResponse | undefined;

      const resolvedCapabilities = Array.isArray(capsPayload?.capabilities)
        ? (capsPayload?.capabilities ?? [])
        : [];
      const uptimeValue =
        typeof metricsPayload?.metrics?.uptimeSeconds === 'number'
          ? metricsPayload.metrics.uptimeSeconds
          : 0;

      setVer(versionInfo);
      setCaps(resolvedCapabilities);
      setUptimeSeconds(uptimeValue);
      announceSuccess('Backend information loaded successfully');
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e);
      setBackendError(errorMsg);
      announceError(`Failed to load backend information: ${errorMsg}`);
    } finally {
      setBackendLoading(false);
    }
  }, [announceError, announceInfo, announceSuccess]);

  useEffect(() => {
    loadBackendInfo();
  }, [loadBackendInfo]);

  /**
   * Initiates the save process for settings by displaying a saving indicator,
   * announcing success upon completion, and resetting indicators after a delay.
   */
  function saveChanges() {
    setSaving(true);
    setSaved(false);
    announceInfo('Saving settings...');
    setTimeout(() => {
      setSaving(false);
      setSaved(true);
      announceSuccess('Settings saved successfully');
      setTimeout(() => setSaved(false), 1200);
    }, 600);
  }

  const handleLmStudioUrlChange = useCallback((e: ChangeEvent<HTMLInputElement>) => {
    setLmStudioUrl(e.target.value);
  }, []);

  const handleLmStudioModelChange = useCallback((e: ChangeEvent<HTMLInputElement>) => {
    setLmStudioModel(e.target.value);
  }, []);

  const handleLmStudioEnabledChange = useCallback(
    (value: boolean) => {
      setLmStudioEnabled(value);
      announceInfo(`LM Studio ${value ? 'enabled' : 'disabled'}`);
    },
    [announceInfo]
  );

  const handleTestLMStudioConnection = useCallback(async () => {
    setLmStudioTesting(true);
    try {
      const response = await fetch(`${lmStudioUrl}/v1/models`);
      if (response.ok) {
        setLmStudioStatus('connected');
        announceSuccess('LM Studio connection successful!');
      } else {
        setLmStudioStatus('disconnected');
        announceError('LM Studio connection failed');
      }
    } catch {
      setLmStudioStatus('disconnected');
      announceError('Unable to connect to LM Studio');
    } finally {
      setLmStudioTesting(false);
    }
  }, [lmStudioUrl, announceSuccess, announceError]);

  const triggerLmStudioTest = useCallback(() => {
    handleTestLMStudioConnection();
  }, [handleTestLMStudioConnection]);

  const handleDarkModeToggle = useCallback(
    (value: boolean) => {
      setDarkMode(value);
      announceInfo(`Dark mode ${value ? 'enabled' : 'disabled'}`);
    },
    [announceInfo]
  );

  const handleNotificationsToggle = useCallback(
    (value: boolean) => {
      setNotifications(value);
      announceInfo(`Notifications ${value ? 'enabled' : 'disabled'}`);
    },
    [announceInfo]
  );

  const handleAutoSaveToggle = useCallback(
    (value: boolean) => {
      setAutoSave(value);
      announceInfo(`Auto-save ${value ? 'enabled' : 'disabled'}`);
    },
    [announceInfo]
  );

  const GeneralSettings: React.FC<{
    darkMode: boolean;
    onDarkModeChange: (value: boolean) => void;
    notifications: boolean;
    onNotificationsChange: (value: boolean) => void;
    autoSave: boolean;
    onAutoSaveChange: (value: boolean) => void;
  }> = ({
    darkMode,
    onDarkModeChange,
    notifications,
    onNotificationsChange,
    autoSave,
    onAutoSaveChange,
  }) => (
    <fieldset style={{ display: 'grid', gap: 10, border: 'none', padding: 0, margin: 0 }}>
      <legend id='general-settings' className='sr-only'>
        General Settings
      </legend>
      <Toggle
        id='dark-mode'
        label='Dark Mode'
        checked={darkMode}
        onChange={onDarkModeChange}
      />
      <Toggle
        id='notifications'
        label='Notifications'
        checked={notifications}
        onChange={onNotificationsChange}
      />
      <Toggle
        id='auto-save'
        label='Auto-save'
        checked={autoSave}
        onChange={onAutoSaveChange}
      />
    </fieldset>
  );

  return (
    <PageContainer className='settings-page'>
      <PageHeader icon={<SettingsIcon width={20} height={20} />} title='Settings' />

      <main role='main' aria-label='Settings configuration'>
        {saved ? (
          <div style={{ marginBottom: 10 }} role='alert' aria-live='polite'>
            <Banner type='success'>Settings saved.</Banner>
          </div>
        ) : null}

        <section style={{ margin: '12px 0' }}>
          <Card title='Backend Integration'>
            <BackendIntegrationDetails
              apiBaseUrl={API_BASE_URL}
              versionInfo={ver}
              uptimeSeconds={uptimeSeconds}
              capabilities={caps}
              onRefresh={loadBackendInfo}
              loading={backendLoading}
              error={backendError}
            />
          </Card>
        </section>

        <section>
          <Card title='LM Studio Configuration'>
            <LMStudioConfig
              url={lmStudioUrl}
              onUrlChange={handleLmStudioUrlChange}
              model={lmStudioModel}
              onModelChange={handleLmStudioModelChange}
              enabled={lmStudioEnabled}
              onEnabledChange={handleLmStudioEnabledChange}
              testing={lmStudioTesting}
              status={lmStudioStatus}
              onTestConnection={triggerLmStudioTest}
            />
          </Card>
        </section>

        <section
          style={{
            display: 'grid',
            gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr',
            gap: 12,
          }}
        >
          <Card title='General Settings'>
            <GeneralSettings
              darkMode={darkMode}
              onDarkModeChange={handleDarkModeToggle}
              notifications={notifications}
              onNotificationsChange={handleNotificationsToggle}
              autoSave={autoSave}
              onAutoSaveChange={handleAutoSaveToggle}
            />
          </Card>

          <Card title='Advanced Settings'>
            {/* ...advanced settings JSX... */}
          </Card>
        </section>
      </main>
    </PageContainer>
  );
              </legend>
              <Toggle
                checked={darkMode}
                onChange={handleDarkModeToggle}
                label='Enable Dark Mode'
                data-testid='dark-mode-toggle'
                aria-label='Enable dark mode'
              />
              <Toggle
                checked={notifications}
                onChange={handleNotificationsToggle}
                label='Enable Notifications'
                data-testid='notifications-toggle'
                aria-label='Enable notifications'
              />
              <Toggle
                checked={autoSave}
                onChange={handleAutoSaveToggle}
                label='Auto-save Changes'
                data-testid='auto-save-toggle'
                aria-label='Enable auto-save'
              />
            </fieldset>
          </Card>

          <Card title='Advanced Settings'>
            <fieldset style={{ display: 'grid', gap: 10, border: 'none', padding: 0, margin: 0 }}>
              <legend id='advanced-settings' className='sr-only'>
                Advanced Settings
              </legend>
              <Toggle
                checked={advancedEnabled}
                onChange={setAdvancedEnabled}
                label='Enable Advanced Mode'
                data-testid='advanced-mode-toggle'
                aria-label='Enable advanced mode'
              />
              <Checkbox
                checked={betaFeatures}
                onChange={setBetaFeatures}
                label='Enable experimental features'
                data-testid='beta-features-checkbox'
                aria-label='Enable experimental features'
              />
              <Checkbox
                checked={telemetry}
                onChange={setTelemetry}
                label='Send anonymous telemetry'
                data-testid='telemetry-checkbox'
                aria-label='Send anonymous telemetry'
              />
            </fieldset>
          </Card>
        </section>

        <div style={{ marginTop: 12 }}>
          <Button
            variant='primary'
            onClick={saveChanges}
            disabled={saving}
            data-testid='save-settings-button'
            aria-label='Save settings'
            style={{
              minWidth: isMobile ? '100%' : 'auto',
            }}
          >
            {saving ? 'Saving…' : 'Save Changes'}
          </Button>
        </div>
      </main>

      {/* Screen reader live region for announcements */}
      <LiveRegion ariaLabel='Settings page announcements' showLatestOnly />
    </PageContainer>
  );
}
