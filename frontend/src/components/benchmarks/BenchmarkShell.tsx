"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

export function Icon({ name, size = 18, className = "" }: { name: "library" | "projects" | "journal" | "plus" | "search" | "filter" | "arrow" | "chevron" | "source"; size?: number; className?: string }) {
  const paths = {
    library: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
    projects: <path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10H3Z" />,
    journal: <path d="M5 3h12a2 2 0 0 1 2 2v16H7a2 2 0 0 1-2-2ZM5 17h14M9 7h6M9 11h6" />,
    plus: <path d="M12 5v14M5 12h14" />,
    search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" /></>,
    filter: <><path d="M4 7h16M4 17h16" /><path d="M8 4v6M16 14v6" /></>,
    arrow: <path d="M4 12h15m-6-6 6 6-6 6" />,
    chevron: <path d="m9 5 7 7-7 7" />,
    source: <path d="M9 15 15 9M7 14l-2 2a3 3 0 0 0 4 4l3-3M12 7l3-3a3 3 0 0 1 4 4l-2 2" />,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">{paths[name]}</svg>;
}

export default function BenchmarkShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const section = pathname.startsWith("/projects") ? "Projects" : pathname.startsWith("/benchmarks") ? "Benchmarks" : "Research journal";
  const nav = [
    { label: "Benchmarks", href: "/benchmarks", icon: "library" },
    { label: "Projects", href: "/projects", icon: "projects" },
    { label: "Research journal", href: "/", icon: "journal" },
  ] as const;
  return <div className="workspace">
    <a href="#content" className="skip-link">Skip to content</a>
    <aside className="workspace-sidebar">
      <Link href="/benchmarks" className="workspace-brand" aria-label="ARIA Researcher home">
        <span className="brand-mark" aria-hidden="true"><svg width="22" height="22" viewBox="0 0 24 24" fill="none"><path d="m4 19 8-15 8 15M8 13h8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /><circle cx="12" cy="19" r="1.5" fill="currentColor" /></svg></span>
        <span>ARIA<span className="brand-caption">Research workspace</span></span>
      </Link>
      <p className="sidebar-label">Workspace</p>
      <nav aria-label="Main navigation" className="workspace-nav">
        {nav.map(item => <Link key={item.href} href={item.href} className={`nav-item ${section === item.label ? "active" : ""}`} aria-current={section === item.label ? "page" : undefined}><Icon name={item.icon} /><span>{item.label}</span></Link>)}
      </nav>
      <div className="sidebar-bottom">
        <Link href="/benchmarks/import" className="nav-item"><Icon name="plus" /><span>Import benchmark</span></Link>
        <div className="workspace-identity"><span className="workspace-avatar">R</span><div>Local workspace<span>Research & experimentation</span></div></div>
      </div>
    </aside>
    <div className="workspace-body">
      <header className="workspace-topbar"><span className="topbar-workspace">Workspace</span><Icon name="chevron" size={13} /><span>{section}</span><span className="workspace-tag">ARIA Researcher</span></header>
      <main id="content" className="workspace-content" tabIndex={-1}>{children}</main>
    </div>
  </div>;
}

export function Notice({ children, error = false }: { children: ReactNode; error?: boolean }) {
  return <div role={error ? "alert" : "status"} className={`notice ${error ? "notice-error" : ""}`}>{children}</div>;
}

export function ExternalLink({ url, children }: { url: string | null | undefined; children: ReactNode }) {
  let safe = false;
  try { safe = !!url && ["https:", "http:"].includes(new URL(url).protocol); } catch { /* invalid source URL */ }
  return safe ? <a href={url!} className="link break-words" target="_blank" rel="noopener noreferrer">{children} <span aria-hidden="true">↗</span></a> : <span>{children}</span>;
}
