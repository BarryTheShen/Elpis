import { useState } from 'preact/hooks';

import type { JSX } from 'preact';

import { ThemeToggle } from '../components/ThemeToggle';
import { login } from '../lib/auth';
import { product } from '../lib/product';

interface LoginPageProps {
  /** Called when the user successfully authenticates. */
  onLogin: () => void;
}

/**
 * Full-screen login form shown when the session cookie is absent or expired.
 * Submits a password to POST /api/auth/login and calls onLogin on success.
 */
export function LoginPage({ onLogin }: LoginPageProps) {
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  /** Handle form submit: send password to the API. */
  async function handleSubmit(e: JSX.TargetedEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!password.trim()) {
      return;
    }
    setLoading(true);
    setError(null);

    try {
      const err = await login(password);
      if (err) {
        setError(err);
        setPassword('');
      } else {
        onLogin();
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-[#f9f8f7] px-4 py-12 text-[#2c2c2b] dark:bg-[#171716] dark:text-[#f4f3f1]">
      <div className="absolute right-4 top-4">
        <ThemeToggle />
      </div>

      <main className="w-full max-w-md">
        <div className="mb-8 flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-md bg-[#2783de] text-base font-black text-white">
            {product.mark}
          </span>
          <div>
            <p className="text-sm font-semibold tracking-tight">{product.name}</p>
            <p className="text-sm text-[#7d7a75] dark:text-[#b4b1ab]">Admin sign-in</p>
          </div>
        </div>

        <section className="border-y border-[#e6e5e3] bg-white px-6 py-8 dark:border-[#3b3a37] dark:bg-[#20201e] sm:px-8">
          <h1 className="text-3xl font-semibold tracking-tight">Welcome back</h1>
          <p className="mt-2 text-base leading-7 text-[#7d7a75] dark:text-[#b4b1ab]">
            Sign in to manage sources, settings, and today&apos;s publication.
          </p>

          <form onSubmit={handleSubmit} className="mt-8 flex flex-col gap-5">
            <div className="flex flex-col gap-2">
              <label
                htmlFor="password"
                className="text-sm font-semibold text-[#2c2c2b] dark:text-[#f4f3f1]"
              >
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onInput={(e) =>
                  setPassword((e.target as HTMLInputElement).value)
                }
                aria-invalid={error ? 'true' : undefined}
                aria-describedby={error ? 'login-error' : undefined}
                placeholder="Enter your password"
                className={[
                  'w-full rounded-md border px-3 py-2.5 text-base outline-none transition-colors',
                  'bg-white dark:bg-[#171716]',
                  'text-[#2c2c2b] dark:text-[#f4f3f1]',
                  'placeholder-[#7d7a75] dark:placeholder-[#b4b1ab]',
                  error
                    ? 'border-[#b9382f] focus:ring-2 focus:ring-[#b9382f]/20'
                    : 'border-[#e6e5e3] focus:border-[#2783de] focus:ring-2 focus:ring-[#2783de]/20 dark:border-[#3b3a37]',
                ].join(' ')}
              />
            </div>

            {error && (
              <p id="login-error" role="alert" className="text-sm leading-6 text-[#b9382f] dark:text-[#ff9f96]">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading || !password.trim()}
              className="inline-flex min-h-11 items-center justify-center gap-2 rounded-md bg-[#2783de] px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[#1f6fbe] active:scale-[0.98] focus-visible:ring-2 focus-visible:ring-[#2783de] disabled:cursor-not-allowed disabled:opacity-50 dark:bg-[#63aaf0] dark:text-[#171716] dark:hover:bg-[#83bdf5]"
            >
              {loading && (
                <span className="h-4 w-4 rounded-full border-2 border-current border-t-transparent animate-spin" />
              )}
              {loading ? 'Signing in...' : 'Sign in'}
            </button>
          </form>
        </section>
      </main>
    </div>
  );
}
