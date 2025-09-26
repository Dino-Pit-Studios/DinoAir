import type { FC, SVGProps } from 'react';

type Props = SVGProps<SVGSVGElement>;

/**
 * Notes icon component.
 *
 * @param props - SVG properties applied to the SVG element.
 * @returns A React element rendering a notes icon.
 */
const Notes: FC<Props> = props => (
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
    <path d='M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z' />
    <path d='M14 2v6h6' />
    <path d='M8 13h8' />
    <path d='M8 17h5' />
  </svg>
);

export default Notes;
