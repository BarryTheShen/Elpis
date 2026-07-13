import type { ComponentChildren } from 'preact';

interface EmptyStateProps {
  title: string;
  description?: string;
  action?: ComponentChildren;
  icon?: ComponentChildren;
}

/** Centered empty-state placeholder. */
export function EmptyState({
  title,
  description,
  action,
  icon,
}: EmptyStateProps) {
  return (
    <div class="flex flex-col items-center justify-center py-20 px-6 text-center">
      {icon && (
        <div class="mb-5 text-[#7d7a75] dark:text-[#b4b1ab]">{icon}</div>
      )}
      <h3 class="text-xl font-semibold tracking-tight text-[#2c2c2b] dark:text-[#f4f3f1]">
        {title}
      </h3>
      {description && (
        <p class="mt-2 text-base leading-7 text-[#7d7a75] dark:text-[#b4b1ab] max-w-prose">
          {description}
        </p>
      )}
      {action && <div class="mt-5">{action}</div>}
    </div>
  );
}
