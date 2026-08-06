import type { ComponentChildren, JSX } from 'preact';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
type Size = 'sm' | 'md';

interface ButtonProps {
  variant?: Variant;
  size?: Size;
  disabled?: boolean;
  loading?: boolean;
  type?: 'button' | 'submit' | 'reset';
  onClick?: JSX.MouseEventHandler<HTMLButtonElement>;
  children: ComponentChildren;
  className?: string;
  title?: string;
}

const VARIANT: Record<Variant, string> = {
  primary:
    'bg-[#2783de] text-white hover:bg-[#1f6fbe] dark:bg-[#63aaf0] dark:text-[#171716] dark:hover:bg-[#83bdf5]',
  secondary:
    'bg-[#f0efed] dark:bg-[#2a2927] text-[#2c2c2b] dark:text-[#f4f3f1] border border-[#e6e5e3] dark:border-[#3b3a37] hover:bg-[#e6e5e3] dark:hover:bg-[#3b3a37]',
  ghost:
    'text-[#7d7a75] dark:text-[#b4b1ab] hover:bg-[#f0efed] dark:hover:bg-[#2a2927] hover:text-[#2c2c2b] dark:hover:text-[#f4f3f1]',
  danger:
    'bg-[#fff1ef] dark:bg-[#4a2521] text-[#b9382f] dark:text-[#ff9f96] border border-[#f4c6c1] dark:border-[#7e3f37] hover:bg-[#ffe4e0] dark:hover:bg-[#63302b]',
};

const SIZE: Record<Size, string> = {
  sm: 'px-2.5 py-1.5 text-xs rounded-md gap-1',
  md: 'px-4 py-2 text-sm rounded-lg gap-1.5',
};

/** Reusable button with variant + size system. */
export function Button({
  variant = 'primary',
  size = 'md',
  disabled = false,
  loading = false,
  type = 'button',
  onClick,
  children,
  className = '',
  title,
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      onClick={onClick}
      title={title}
      className={[
        'transition-colors select-none disabled:opacity-50 disabled:cursor-not-allowed',
        'active:scale-[0.98] focus-visible:ring-2 focus-visible:ring-[#2783de] focus-visible:ring-offset-2 dark:focus-visible:ring-offset-[#171716]',
        VARIANT[variant],
        SIZE[size],
        className,
      ].join(' ')}
    >
      {loading && (
        <span
          className={`inline-block rounded-full border-current border-t-transparent animate-spin ${
            size === 'sm' ? 'w-3 h-3 border-[1.5px]' : 'w-3.5 h-3.5 border-2'
          }`}
        />
      )}
      {children}
    </button>
  );
}
