interface TelemetryData {
  cpu: string;
  mem: string;
  latency: string;
}

interface TelemetryBarProps {
  telemetry: TelemetryData;
}

/**
 * Renders a telemetry bar displaying CPU, memory, and latency metrics.
 *
 * @param {TelemetryBarProps} props - The TelemetryBar component props.
 * @param {TelemetryBarProps['telemetry']} props.telemetry - Object containing telemetry metrics (cpu, mem, latency).
 * @returns {JSX.Element} The rendered telemetry bar component.
 */
export default function TelemetryBar({ telemetry }: TelemetryBarProps) {
  return (
    <section
      style={{
        marginTop: 12,
        background: '#16213e',
        border: '1px solid #2a3b7a',
        borderRadius: 8,
        padding: '10px 12px',
        display: 'flex',
        justifyContent: 'space-between',
        color: '#e6eaff',
        fontSize: 14,
      }}
    >
      <span role='group' aria-label='CPU usage'>
        CPU:{' '}
        <output className='metric' aria-label={`CPU usage is ${telemetry.cpu}`}>
          {telemetry.cpu}
        </output>
      </span>
      <span role='group' aria-label='Memory usage'>
        Memory:{' '}
        <output className='metric' aria-label={`Memory usage is ${telemetry.mem}`}>
          {telemetry.mem}
        </output>
      </span>
      <span role='group' aria-label='Latency'>
        Latency:{' '}
        <output className='metric' aria-label={`Latency is ${telemetry.latency}`}>
          {telemetry.latency}
        </output>
      </span>
    </section>
  );
}
