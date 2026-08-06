import { Link } from 'wouter';

interface AuthRequiredPageProps {
  title: string;
  description: string;
  returnTo?: string;
}

/** Explains why a personal publication list needs an authenticated session. */
export function AuthRequiredPage({
  title,
  description,
  returnTo = '/',
}: AuthRequiredPageProps) {
  return (
    <section className="mx-auto max-w-xl py-12 text-center sm:py-20" aria-labelledby="auth-required-heading">
      <p className="text-sm font-medium text-[#1d5f9f] dark:text-[#a6d2f8]">Personal reading</p>
      <h1 id="auth-required-heading" className="mt-3 text-3xl font-semibold tracking-[-0.03em] text-[#2c2c2b] dark:text-[#f4f3f1]">
        {title}
      </h1>
      <p className="mx-auto mt-3 max-w-prose text-base leading-7 text-[#7d7a75] dark:text-[#b4b1ab]">
        {description}
      </p>
      <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
        <Link
          href={`/login?next=${encodeURIComponent(returnTo)}`}
          className="inline-flex min-h-11 items-center rounded-lg bg-[#2783de] px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[#1f6fbe] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2783de] dark:bg-[#63aaf0] dark:text-[#171716] dark:hover:bg-[#83bdf5]"
        >
          Sign in
        </Link>
        <Link
          href="/"
          className="inline-flex min-h-11 items-center rounded-lg border border-[#e6e5e3] px-4 py-2.5 text-sm font-semibold text-[#2c2c2b] transition-colors hover:bg-[#f0efed] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2783de] dark:border-[#3b3a37] dark:text-[#f4f3f1] dark:hover:bg-[#2a2927]"
        >
          Return to today
        </Link>
      </div>
    </section>
  );
}
