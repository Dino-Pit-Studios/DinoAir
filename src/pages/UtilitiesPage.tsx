// no React default import needed with react-jsx

import OtherToolsPage from '../components/icons/OtherToolsPage';
import PageContainer from '../components/layout/PageContainer';
import PageHeader from '../components/layout/PageHeader';
import CalendarCard from '../components/utilities/CalendarCard';
import SmartTimerCard from '../components/utilities/SmartTimerCard';
import TelemetryBar from '../components/utilities/TelemetryBar';

export default function UtilitiesPage() {
  // Telemetry placeholders
  const telemetry = {
    cpu: '23%',
    mem: '3.2 GB',
    latency: '120 ms',
  };

  return (
    <PageContainer className='utilities-page'>
      <PageHeader icon={<OtherToolsPage width={20} height={20} />} title='Utilities' />

      <section style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <SmartTimerCard />
        <CalendarCard />
      </section>

      <TelemetryBar telemetry={telemetry} />
    </PageContainer>
  );
}
