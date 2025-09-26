import type { FC, SVGProps } from 'react';

type Props = SVGProps<SVGSVGElement>;

/**
 * Chat icon component.
 *
 * Renders a chat bubble SVG icon.
 *
 * @param {Props} props - SVG props for the icon component.
 * @returns {JSX.Element} SVG element representing the chat icon.
 */
const Chat: FC<Props> = props => (
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
    <path d='M21 15a4 4 0 0 1-4 4H8l-4 3V7a4 4 0 0 1 4-4h9a4 4 0 0 1 4 4z' />
    <path d='M8 10h8' />
    <path d='M8 13h5' />
  </svg>
);

export default Chat;
