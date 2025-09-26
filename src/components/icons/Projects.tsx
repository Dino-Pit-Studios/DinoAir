import type { FC, SVGProps } from 'react';

type Props = SVGProps<SVGSVGElement>;

/**
 * Projects icon component.
 *
 * @param props - SVG props to apply to the Projects icon.
 * @returns JSX.Element representing the Projects icon.
 */
const Projects: FC<Props> = props => (
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
    <rect x='3' y='4' width='6' height='16' rx='2' />
    <rect x='11' y='4' width='4' height='8' rx='2' />
    <rect x='17' y='4' width='4' height='12' rx='2' />
  </svg>
);

export default Projects;
