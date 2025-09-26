import { useState, useCallback, type FC, type ReactNode } from 'react';

/**
 * FooterLinks component renders a set of navigational links in the footer.
 * @returns {JSX.Element} The container with footer links.
 */
export default function FooterLinks() {
  const base = '#9ca3af';
  const hover = '#e5e7eb';

  /**
   * LinkItem renders an anchor element with hover effect changing link color.
   * @param {string} href - The URL to navigate to.
   * @param {ReactNode} children - The link text or elements.
   * @returns {JSX.Element} The rendered link element.
   */
  const LinkItem: FC<{ href: string; children: ReactNode }> = ({ href, children }) => {
    const [h, setH] = useState(false);
    const handleMouseEnter = useCallback(() => {
      setH(true);
    }, []);
    const handleMouseLeave = useCallback(() => {
      setH(false);
    }, []);
    return (
      <a
        href={href}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        style={{
          color: h ? hover : base,
          textDecoration: 'none',
          fontSize: 13,
        }}
      >
        {children}
      </a>
    );
  };

  return (
    <div
      style={{
        display: 'flex',
        gap: 14,
        alignItems: 'center',
        flexWrap: 'wrap',
      }}
    >
      <LinkItem href='#'>Privacy Policy</LinkItem>
      <span aria-hidden='true' style={{ opacity: 0.5 }}>
        •
      </span>
      <LinkItem href='#'>Terms of Service</LinkItem>
      <span aria-hidden='true' style={{ opacity: 0.5 }}>
        •
      </span>
      <LinkItem href='#'>Contact Us</LinkItem>
    </div>
  );
}
