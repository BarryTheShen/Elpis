import type { ComponentChildren } from 'preact';

interface CardProps {
  children: ComponentChildren;
  className?: string;
  /** Remove default padding for tables or custom-padded content. */
  noPad?: boolean;
}

/** Standard bordered surface with restrained elevation. */
export function Card({ children, className = '', noPad = false }: CardProps) {
  return (
    <div
      class={[
        'bg-white dark:bg-[#20201e] border border-[#e6e5e3] dark:border-[#3b3a37]',
        'rounded-lg',
        noPad ? '' : 'p-5',
        className,
      ].join(' ')}
    >
      {children}
    </div>
  );
}

interface CardHeaderProps {
  title: string;
  description?: string;
  actions?: ComponentChildren;
}

/** Card header row with title, optional description and action slot. */
export function CardHeader({ title, description, actions }: CardHeaderProps) {
  return (
    <div class="flex items-start justify-between gap-4 mb-4">
      <div>
        <h2 class="text-base font-semibold text-[#2c2c2b] dark:text-[#f4f3f1]">
          {title}
        </h2>
        {description && (
          <p class="mt-0.5 text-sm text-[#7d7a75] dark:text-[#b4b1ab]">
            {description}
          </p>
        )}
      </div>
      {actions && <div class="flex-shrink-0">{actions}</div>}
    </div>
  );
}
