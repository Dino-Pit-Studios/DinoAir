import { useMemo } from 'react';

import Card from '../common/Card';

const monthNames = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
];

const weekdayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

/**
 * CalendarCard component that renders a calendar view for the current month and year.
 *
 * @returns A React element containing the calendar card.
 */
export default function CalendarCard() {
  const calendar = useMemo(() => {
    const today = new Date();
    const year = today.getFullYear();
    const month = today.getMonth();

    const firstDay = new Date(year, month, 1);
    const startWeekday = firstDay.getDay(); // 0..6 (Sun..Sat)
    const daysInMonth = new Date(year, month + 1, 0).getDate();

    const cells: (number | null)[] = Array(startWeekday)
      .fill(null)
      .concat(Array.from({ length: daysInMonth }, (_, i) => i + 1));
    while (cells.length % 7 !== 0) {
      cells.push(null);
    }
    return { cells, month, year };
  }, []);

  return (
    <Card title='Calendar'>
      <div style={{ display: 'grid', gap: 8 }}>
        <strong style={{ fontSize: 16 }}>
          {monthNames[calendar.month]} {calendar.year}
        </strong>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(7, 1fr)',
            gap: 6,
            fontSize: 13,
            color: '#cdd6ff',
          }}
        >
          {weekdayNames.map(w => (
            <div key={w} style={{ textAlign: 'center', opacity: 0.85 }}>
              {w}
            </div>
          ))}
          {calendar.cells.map((d, idx) => (
            <div
              key={`calendar-cell-${idx}`}
              style={{
                height: 34,
                display: 'grid',
                placeItems: 'center',
                background: d ? '#0f3460' : 'transparent',
                border: d ? '1px solid #2a3b7a' : '1px solid transparent',
                borderRadius: 6,
                color: d ? '#e6eaff' : 'transparent',
              }}
            >
              {d ?? '·'}
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}
