import type { CSSProperties, InputHTMLAttributes } from 'react';

interface SearchInputProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, 'onChange' | 'type' | 'value'> {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}

/**
 * SearchInput component renders a styled search input field.
 *
 * @param {string} value - The current value of the input.
 * @param {(value: string) => void} onChange - Callback invoked when input value changes.
 * @param {string} [placeholder] - Placeholder text displayed when input is empty.
 * @param {string} [className='search-input'] - Additional CSS class name for the input.
 * @param {CSSProperties} [style] - Inline styles to apply to the input.
 * @param {object} restProps - Additional props to pass to the input element.
 * @returns {JSX.Element} A styled search input element.
 */
export default function SearchInput({
  value,
  onChange,
  placeholder,
  className = 'search-input',
  style,
  ...restProps
}: SearchInputProps) {
  const responsiveStyle: CSSProperties = {
    background: '#0f3460',
    border: '1px solid #2a3b7a',
    borderRadius: 6,
    color: '#e6eaff',
    padding: '8px 10px',
    fontSize: 14,
    width: '100%',
    outline: 'none',
    transition: 'border-color 0.2s, box-shadow 0.2s',
    ...style,
  };

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      onChange(e.target.value);
    },
    [onChange]
  );

  return (
    <input
      className={className}
      type='text'
      value={value}
      onChange={handleChange}
      placeholder={placeholder ?? 'Search...'}
      style={responsiveStyle}
      aria-label={restProps['aria-label'] || placeholder || 'Search input'}
      {...restProps}
    />
  );
}
