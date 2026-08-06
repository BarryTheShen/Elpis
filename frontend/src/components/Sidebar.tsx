import { Link, useLocation } from 'wouter';

interface SidebarProps {
  onClose?: () => void;
}

interface NavSection {
  label: string;
  links: Array<{ href: string; label: string; exact?: boolean }>;
}

const SECTIONS: NavSection[] = [
  {
    label: 'Configure',
    links: [
      { href: '/admin/sources', label: 'Sources' },
      { href: '/admin/llm', label: 'LLM' },
      { href: '/admin/providers', label: 'Providers' },
      { href: '/admin/schedule', label: 'Schedule' },
      { href: '/admin/digest-settings', label: 'Digest settings' },
      { href: '/admin/profile', label: 'Profile' },
      { href: '/admin/security', label: 'Security' },
      { href: '/admin/budget', label: 'Budget' },
    ],
  },
  {
    label: 'System',
    links: [
      { href: '/admin/overview', label: 'Overview' },
      { href: '/admin/logs', label: 'Logs' },
      { href: '/admin/advanced', label: 'Advanced' },
    ],
  },
];

/**
 * Left navigation sidebar for configuration and operational tools.
 */
export function Sidebar({ onClose }: SidebarProps) {
  const [location] = useLocation();

  function isActive(href: string, exact = false): boolean {
    if (exact) return location === href;
    return location === href || location.startsWith(href + '/');
  }

  function handleLinkClick() {
    onClose?.();
  }

  return (
    <aside className="flex flex-col h-full overflow-y-auto bg-white dark:bg-[#20201e] border-r border-[#e6e5e3] dark:border-[#3b3a37] py-5 px-3 gap-1">
      {SECTIONS.map((section) => (
        <div key={section.label} className="mb-4">
          <p className="px-3 mb-1 text-xs font-semibold tracking-[0.12em] text-[#7d7a75] dark:text-[#b4b1ab]">
            {section.label}
          </p>

          {section.links.map(({ href, label, exact }) => (
            <Link
              key={href}
              href={href}
              onClick={handleLinkClick}
              className={[
                'flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors no-underline',
                isActive(href, exact)
                  ? 'bg-[#e5f2fc] dark:bg-[#1c3852] text-[#1d5f9f] dark:text-[#a6d2f8] font-semibold'
                  : 'text-[#7d7a75] dark:text-[#b4b1ab] hover:bg-[#f0efed] dark:hover:bg-[#2a2927] hover:text-[#2c2c2b] dark:hover:text-[#f4f3f1]',
              ].join(' ')}
            >
              {label}
            </Link>
          ))}
        </div>
      ))}
    </aside>
  );
}
