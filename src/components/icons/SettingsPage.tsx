import type { FC, SVGProps } from 'react';

type Props = SVGProps<SVGSVGElement>;

/**
 * SettingsPage icon component.
 *
 * @param props - SVG props applied to the SVG element.
 * @returns SVG element representing the SettingsPage icon.
 */
const SettingsPage: FC<Props> = props => (
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
    <line x1='4' y1='6' x2='20' y2='6' />
    <circle cx='8' cy='6' r='2' />
    <line x1='4' y1='12' x2='20' y2='12' />
    <circle cx='16' cy='12' r='2' />
    <line x1='4' y1='18' x2='20' y2='18' />
    <circle cx='12' cy='18' r='2' />
  </svg>
);

export default SettingsPage;
