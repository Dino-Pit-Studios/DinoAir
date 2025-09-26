import { useId, useCallback, type CSSProperties, type ChangeEvent } from 'react';

interface ToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label?: string;
}

/**
 * Renders a toggle switch component.
 *
 * @param {object} props - The component props.
 * @param {boolean} props.checked - Indicates if the toggle is on.
 * @param {(checked: boolean) => void} props.onChange - Callback for state change.
 * @param {string} [props.label] - Optional label displayed next to the toggle.
 * @returns {JSX.Element} The rendered Toggle component.
 */
export default function Toggle({ checked, onChange, label }: ToggleProps) {
  const id = useId();

  const track: CSSProperties = {
    width: 44,
    height: 24,
    background: checked ? '#32bc9b' : '#2a3b7a',
    borderRadius: 12,
    position: 'relative',
    transition: 'background 0.15s ease',
    display: 'inline-block',
    verticalAlign: 'middle',
  };

  const thumb: CSSProperties = {
    position: 'absolute',
    top: 2,
    left: checked ? 22 : 2,
    width: 20,
    height: 20,
    borderRadius: '50%',
    background: '#0b1020',
    transition: 'left 0.15s ease',
    boxShadow: '0 0 0 1px rgba(0,0,0,0.3)',
  };

  const labelStyle: CSSProperties = {
    marginLeft: 10,
    color: '#e6eaff',
    fontSize: 14,
    userSelect: 'none',
  };

  const handleChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      onChange(e.target.checked);
    },
    [onChange]
  );

  return (
    <label
      htmlFor={id}
      className='toggle'
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        cursor: 'pointer',
      }}
    >
      <span role='switch' aria-checked={checked} aria-label={label} style={track}>
        <span style={thumb} />
      </span>
      <input
        id={id}
        type='checkbox'
        checked={checked}
        onChange={handleChange}
        style={{
          position: 'absolute',
          opacity: 0,
          pointerEvents: 'none',
          width: 0,
          height: 0,
        }}
      />
      {label ? <span style={labelStyle}>{label}</span> : null}
    </label>
  );
}
