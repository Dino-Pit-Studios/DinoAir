import type { FC, SVGProps } from 'react';

type Props = SVGProps<SVGSVGElement>;

/**
 * LocalFileRetrievalAndIndexing icon component.
 *
 * Renders an SVG icon representing local file retrieval and indexing.
 *
 * @param props - SVGProps passed to the svg element.
 * @returns JSX Element for the icon.
 */
const LocalFileRetrievalAndIndexing: FC<Props> = props => (
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
    <path d='M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z' />
    <circle cx='17' cy='17' r='3' />
    <path d='M19 19l2 2' />
  </svg>
);

export default LocalFileRetrievalAndIndexing;
