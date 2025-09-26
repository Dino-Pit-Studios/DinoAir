import type { CSSProperties, ReactNode } from 'react';

interface CardProps {
  title?: string;
  children: ReactNode;
  footer?: ReactNode;
  style?: CSSProperties;
}

/**
 * Card component to display content in a styled card layout.
 *
 * @param {string} [title] - The title text to display in the card header.
 * @param {React.ReactNode} children - The main content of the card.
 * @param {React.ReactNode} [footer] - The content to display in the card footer.
 * @param {React.CSSProperties} [style] - Additional inline styles for the card container.
 * @returns {JSX.Element} The rendered Card component.
 */
export default function Card({ title, children, footer, style }: CardProps) {
  return (
    <section
      className='card'
      style={{
        background: '#111827',
        border: '1px solid #1f2937',
        borderRadius: 10,
        padding: 16,
        color: '#e5e7eb',
        boxShadow: '0 1px 2px rgba(0,0,0,0.5)',
        ...style,
      }}
    >
      {title ? (
        <header
          style={{
            marginBottom: 8,
            borderBottom: '1px solid #1f2937',
            paddingBottom: 6,
          }}
        >
          <h3 style={{ margin: 0, fontSize: 16 }}>{title}</h3>
        </header>
      ) : null}
      <div>{children}</div>
      {footer ? (
        <footer
          style={{
            marginTop: 10,
            borderTop: '1px solid #1f2937',
            paddingTop: 8,
          }}
        >
          {footer}
        </footer>
      ) : null}
    </section>
  );
}
