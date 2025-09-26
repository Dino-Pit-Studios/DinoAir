import { useId } from 'react';

interface CheckboxProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label?: string;
}

/**
 * Checkbox component for rendering a styled checkbox input with an optional label.
 *
 * @param {object} props - The properties object.
 * @param {boolean} props.checked - Determines if the checkbox is checked.
 * @param {function} props.onChange - Callback invoked with the new checked state when the checkbox value changes.
 * @param {string} [props.label] - Optional label text displayed next to the checkbox.
 * @returns {JSX.Element} The rendered checkbox component.
 */
export default function Checkbox({ checked, onChange, label }: CheckboxProps) {
  const id = useId();

  const handleChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      onChange(e.target.checked);
    },
    [onChange]
  );

  return (
    <label
      htmlFor={id}
      className='checkbox'
      style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}
    >
      <input
        id={id}
        type='checkbox'
        checked={checked}
        onChange={handleChange}
        style={{
          width: 16,
          height: 16,
          appearance: 'none',
          background: checked ? '#32bc9b' : '#0f3460',
          border: '1px solid #2a3b7a',
          borderRadius: 3,
          outline: 'none',
          display: 'grid',
          placeItems: 'center',
        }}
      />
      {label ? <span style={{ color: '#e6eaff', fontSize: 14 }}>{label}</span> : null}
    </label>
  );
}
