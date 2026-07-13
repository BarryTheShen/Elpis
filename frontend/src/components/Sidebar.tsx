import { Link, useLocation } from 'wouter';
import { formatDigestLabel } from '../lib/dates';
import type { DigestEntry } from '../lib/types';

interface SidebarProps {
  digests: DigestEntry[];
  currentDigestId?: number | null;
  onClose?: () => void;
}

interface NavSection {
  label: string;
  links: Array<{ href: string; label: string; exact?: boolean }>;
}

const SECTIONS: NavSection[] = [
  {
    label: 'Read',
    links: [
      { href: '/admin/digest', label: 'Latest digest', exact: true },
      { href: '/admin/read-later', label: 'Read Later' },
      { href: '/admin/starred', label: 'Starred' },
    ],
  },
  {
    label: 'Configure',
    links: [
      { href: '/admin/sources', label: 'Sources' },
      { href: '/admin/llm', label: 'LLM' },
      { href: '/admin/keys', label: 'API keys' },
      { href: '/admin/schedule', label: 'Schedule' },
      { href: '/admin/digest-settings', label: 'Digest' },
      { href: '/admin/profile', label: 'Profile' },
      { href: '/admin/security', label: 'Security' },
      { href: '/admin/budget', label: 'Budget' },
      { href: '/admin/logs', label: 'Logs' },
    ],
  },
];

/**
 * Left navigation sidebar.
 * Shows nav sections + recent digest history.
 */
export function Sidebar({
  digests,
  currentDigestId,
  onClose,
}: SidebarProps) {
  const [location] = useLocation();

  function isActive(href: string, exact = false): boolean {
    if (exact) return location === href;
    return location === href || location.startsWith(href + '/');
  }

  function handleLinkClick() {
    onClose?.();
  }

  return (
    <aside class="flex flex-col h-full overflow-y-auto bg-white dark:bg-[#20201e] border-r border-[#e6e5e3] dark:border-[#3b3a37] py-5 px-3 gap-1">
      {SECTIONS.map((section) => (
        <div key={section.label} class="mb-4">
          <p class="px-3 mb-1 text-xs font-semibold tracking-[0.12em] text-[#7d7a75] dark:text-[#b4b1ab]">
            {section.label}
          </p>

          {section.links.map(({ href, label, exact }) => (
            <Link
              key={href}
              href={href}
              onClick={handleLinkClick}
              class={[
                'flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors no-underline',
                isActive(href, exact)
                  ? 'bg-[#e5f2fc] dark:bg-[#1c3852] text-[#1d5f9f] dark:text-[#a6d2f8] font-semibold'
                  : 'text-[#7d7a75] dark:text-[#b4b1ab] hover:bg-[#f0efed] dark:hover:bg-[#2a2927] hover:text-[#2c2c2b] dark:hover:text-[#f4f3f1]',
              ].join(' ')}
            >
              {label}
            </Link>
          ))}

          {/* Digest history under "Read" */}
          {section.label === 'Read' && digests.length > 0 && (
            <ul class="mt-1 space-y-0.5">
              {digests.slice(0, 8).map((d) => (
                <li key={d.id}>
                  <Link
                    href={`/?id=${d.id}`}
                    onClick={handleLinkClick}
                    class={[
                      'flex items-center px-3 py-1.5 rounded-lg text-xs transition-colors no-underline truncate',
                      currentDigestId === d.id
                        ? 'bg-[#e5f2fc] dark:bg-[#1c3852] text-[#1d5f9f] dark:text-[#a6d2f8] font-semibold'
                        : 'text-[#7d7a75] dark:text-[#b4b1ab] hover:bg-[#f0efed] dark:hover:bg-[#2a2927] hover:text-[#2c2c2b] dark:hover:text-[#f4f3f1]',
                    ].join(' ')}
                  >
                    #{d.id} · {formatDigestLabel(d.created_at)}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </aside>
  );
}
