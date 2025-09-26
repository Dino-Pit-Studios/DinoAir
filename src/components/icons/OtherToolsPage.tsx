import type { FC, SVGProps } from 'react';

type Props = SVGProps<SVGSVGElement>;

/**
 * Renders the "Other Tools" icon as an SVG component.
 *
 * @param props - SVG properties passed to the SVG element.
 * @returns The SVG element representing the Other Tools icon.
 */
const OtherToolsPage: FC<Props> = props => (
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
    <rect x='3' y='7' width='18' height='13' rx='2' />
    <path d='M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2' />
    <path d='M3 12h18' />
  </svg>
);

export default OtherToolsPage;
