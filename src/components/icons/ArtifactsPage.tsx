import type { FC, SVGProps } from 'react';

type Props = SVGProps<SVGSVGElement>;

/**
 * ArtifactsPage icon component.
 * Renders an SVG icon representing an artifacts page.
 *
 * @param props - SVG props for the SVG element.
 * @returns JSX.Element representing the icon.
 */
const ArtifactsPage: FC<Props> = props => (
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
    <path d='M8 9h3' />
    <path d='M8 13h8' />
    <path d='M8 17h8' />
  </svg>
);

export default ArtifactsPage;
