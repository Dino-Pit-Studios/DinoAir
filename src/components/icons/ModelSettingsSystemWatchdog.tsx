import type { FC, SVGProps } from 'react';

type Props = SVGProps<SVGSVGElement>;

/**
 * ModelSettingsSystemWatchdog icon component.
 *
 * @param {Props} props - SVG properties passed to the icon component.
 * @returns {JSX.Element} The rendered SVG icon for the system watchdog settings.
 */
const ModelSettingsSystemWatchdog: FC<Props> = props => (
  <svg
    viewBox='0 0 24 24'
    width='24'
    height='24'
    fill='none'
    stroke='currentColor'
    strokeWidth={2}
    strokeLinecap='round'
    strokeLinejoin='round'
    {...props}
  >
    <rect x='3' y='4' width='18' height='14' rx='2' />
    <path d='M8 21h8' />
    <path d='M12 18v3' />
    <path d='M7 11l2 2 2-4 2 6 2-3' />
  </svg>
);

export default ModelSettingsSystemWatchdog;
