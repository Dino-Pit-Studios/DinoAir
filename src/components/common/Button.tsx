import {
  useCallback,
  useState,
  type ButtonHTMLAttributes,
  type CSSProperties,
  type ReactNode,
} from 'react';

type ButtonVariant = 'primary' | 'secondary' | 'ghost';

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode;
  variant?: ButtonVariant;
};

export default function Button({
  children,
  variant = 'primary',
  disabled,
  style,
  ...rest
}: ButtonProps) {
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);

  const handleMouseEnter = useCallback(() => {
    if (!disabled) {
      setHovered(true);
    }
  }, [disabled]);

  const handleMouseLeave = useCallback(() => {
    setHovered(false);
  }, []);

  const handleFocus = useCallback(() => {
    setFocused(true);
  }, []);

  const handleBlur = useCallback(() => {
    setFocused(false);
  }, []);

  const base: CSSProperties = {
    height: 38,
    padding: '0 14px',
    borderRadius: 8,
    fontSize: 14,
    fontWeight: 500,
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.5 : 1,
    transition: 'all 0.15s ease',
    outline: focused ? '2px solid #60a5fa' : 'none',
    outlineOffset: 2,
    border: '1px solid transparent',
    background: 'transparent',
    color: '#e5e7eb',
  };

  const variants: Record<ButtonVariant, CSSProperties> = {
    primary: {
      background: hovered ? '#1d4ed8' : '#2563eb',
      color: '#ffffff',
    },
    secondary: {
      background: hovered ? '#4b5563' : '#374151',
      color: '#e5e7eb',
    },
    ghost: {
      background: hovered ? 'rgba(255,255,255,0.06)' : 'transparent',
      color: '#e5e7eb',
    },
  };

  return (
    <button
      className='btn'
      disabled={disabled}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onFocus={handleFocus}
      onBlur={handleBlur}
      style={{ ...base, ...variants[variant], ...style }}
      {...rest}
    >
      {children}
    </button>
  );
}
