import { useEffect, useState } from 'react';

import Button from '../common/Button';
import Card from '../common/Card';

/**
 * SmartTimerCard component that displays a timer with start, stop, and reset controls.
 * @returns {JSX.Element} The rendered SmartTimerCard component.
 */
export default function SmartTimerCard() {
  const [running, setRunning] = useState(false);
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    if (!running) {
      return;
    }
    const id = setInterval(() => setSeconds(s => s + 1), 1000);
    return () => clearInterval(id);
  }, [running]);

  const start = useCallback(() => setRunning(true), []);
  const stop = useCallback(() => setRunning(false), []);

  /**
   * Resets the timer to zero and stops the timer.
   * @returns {void}
   */
  const reset = useCallback(() => {
    setSeconds(0);
    setRunning(false);
  }, []);

  return (
    <Card title='Smart Timer'>
      <div style={{ display: 'grid', gap: 10 }}>
        <div style={{ fontSize: 32, fontWeight: 700 }}>
          {String(Math.floor(seconds / 60)).padStart(2, '0')}:
          {String(seconds % 60).padStart(2, '0')}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <Button variant='primary' onClick={start} disabled={running}>
            Start
          </Button>
          <Button variant='secondary' onClick={stop} disabled={!running}>
            Stop
          </Button>
          <Button variant='ghost' onClick={reset}>
            Reset
          </Button>
        </div>
      </div>
    </Card>
  );
}
