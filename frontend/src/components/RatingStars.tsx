interface RatingStarsProps {
  value: number | null | undefined;
  onChange: (rating: number) => void;
  disabled?: boolean;
}

const STARS = [1, 2, 3, 4, 5];

const LABELS = ['Terrible', 'Poor', 'OK', 'Good', 'Excellent'];

/** 1-5 star rating input. */
export function RatingStars({
  value,
  onChange,
  disabled = false,
}: RatingStarsProps) {
  return (
    <div class="flex shrink-0 gap-1" role="group" aria-label="Rating">
      {STARS.map((n) => {
        const active = (value ?? 0) >= n;
        return (
          <button
            key={n}
            type="button"
            disabled={disabled}
            onClick={() => onChange(n)}
            title={LABELS[n - 1]}
            aria-label={`Rate ${n} star${n !== 1 ? 's' : ''}`}
            class={[
              'w-8 h-8 flex items-center justify-center rounded-md text-sm font-semibold',
              'border transition-all cursor-pointer select-none active:scale-[0.96]',
              'disabled:opacity-50 disabled:cursor-not-allowed',
              'focus-visible:ring-2 focus-visible:ring-[#2783de] focus-visible:ring-offset-2',
              active
                ? 'border-[#2783de] bg-[#e5f2fc] dark:border-[#63aaf0] dark:bg-[#1c3852] text-[#1d5f9f] dark:text-[#a6d2f8]'
                : 'border-[#e6e5e3] dark:border-[#3b3a37] bg-white dark:bg-[#20201e] text-[#7d7a75] dark:text-[#b4b1ab] hover:border-[#2783de] hover:text-[#1d5f9f] dark:hover:border-[#63aaf0] dark:hover:text-[#a6d2f8]',
            ].join(' ')}
          >
            {n}
          </button>
        );
      })}
    </div>
  );
}
