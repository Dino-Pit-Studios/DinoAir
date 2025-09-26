import type { FC, SVGProps } from 'react';

type Props = SVGProps<SVGSVGElement>;

/**
 * Renders a home icon as an SVG element.
 *
 * @param props - SVG properties to apply to the svg element.
 * @returns A React functional component rendering a home icon.
 */
const Home: FC<Props> = props => (
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
    <path d='M3 10l9-7 9 7v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z' />
    <path d='M9 22V12h6v10' />
  </svg>
);

export default Home;
