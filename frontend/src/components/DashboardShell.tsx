"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import ThemeToggle from "./ThemeToggle";

const navigation = [
  { href: "/", label: "Overview" },
  { href: "/pipelines", label: "Pipeline Network" },
  { href: "/methane", label: "Methane Observations" },
  { href: "/sensors", label: "Sensor Monitoring" },
  { href: "/risk", label: "Risk Analysis" },
  { href: "/assistant", label: "AI Analyst" },
];

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

function getFocusableElements(container: HTMLElement) {
  return Array.from(
    container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
  ).filter((element) => element.getAttribute("aria-hidden") !== "true");
}

function Navigation({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();

  return (
    <nav aria-label="Main navigation" className="space-y-2 text-sm">
      {navigation.map((item) => {
        const isActive = pathname === item.href;

        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={onNavigate}
            aria-current={isActive ? "page" : undefined}
            className={`block rounded-lg px-4 py-3 transition ${
              isActive
                ? "border border-accent/25 bg-accent/10 text-accent"
                : "text-muted hover:bg-surface-hover hover:text-foreground"
            }`}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}

function Brand() {
  return (
    <div className="flex items-center gap-3">
      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent/15 text-accent">
        <span className="text-xl">M</span>
      </div>
      <div>
        <h1 className="font-semibold tracking-wide">MethaTrace</h1>
        <p className="text-xs text-muted">Methane Intelligence</p>
      </div>
    </div>
  );
}

function MonitoringArea() {
  return (
    <div className="rounded-xl border border-border bg-surface-raised p-4">
      <p className="text-xs text-muted">MONITORING AREA</p>
      <p className="mt-2 font-medium">Chakan Industrial Zone</p>
      <p className="mt-1 text-xs text-muted">Maharashtra, India</p>
    </div>
  );
}

export default function DashboardShell({
  children,
  headerActions,
}: {
  children: ReactNode;
  headerActions?: ReactNode;
}) {
  const pathname = usePathname();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const drawerRef = useRef<HTMLElement>(null);
  const previousPathname = useRef(pathname);
  const menuWasOpen = useRef(false);

  const closeMobileMenu = useCallback(() => {
    setMobileMenuOpen(false);
  }, []);

  useEffect(() => {
    if (previousPathname.current === pathname) return;
    previousPathname.current = pathname;
    setMobileMenuOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (mobileMenuOpen) {
      menuWasOpen.current = true;
      return;
    }

    if (menuWasOpen.current) {
      menuWasOpen.current = false;
      menuButtonRef.current?.focus();
    }
  }, [mobileMenuOpen]);

  useEffect(() => {
    if (!mobileMenuOpen) return;

    const drawer = drawerRef.current;
    if (!drawer) return;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const focusable = getFocusableElements(drawer);
    focusable[0]?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setMobileMenuOpen(false);
        return;
      }

      if (event.key !== "Tab") return;

      const elements = getFocusableElements(drawer);
      if (elements.length === 0) {
        event.preventDefault();
        return;
      }

      const first = elements[0];
      const last = elements[elements.length - 1];

      if (!drawer.contains(document.activeElement)) {
        event.preventDefault();
        first.focus();
        return;
      }

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [mobileMenuOpen]);

  const pageTitle =
    navigation.find((item) => item.href === pathname)?.label ?? "Overview";

  return (
    <main className="min-h-dvh bg-background text-foreground">
      <aside className="fixed inset-y-0 left-0 z-30 hidden h-dvh w-64 overflow-y-auto border-r border-border bg-sidebar p-6 lg:flex lg:flex-col">
        <div className="mb-12">
          <Brand />
        </div>
        <p className="mb-4 text-xs font-semibold uppercase tracking-widest text-subtle">
          Workspace
        </p>
        <Navigation />
        <div className="mt-auto space-y-4 pt-6">
          <ThemeToggle className="w-full" />
          <MonitoringArea />
        </div>
      </aside>

      {mobileMenuOpen && (
        <div
          className="fixed inset-0 z-40 bg-overlay lg:hidden"
          onClick={closeMobileMenu}
          aria-hidden="true"
        />
      )}

      <aside
        id="mobile-navigation"
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-label="Main navigation"
        aria-hidden={mobileMenuOpen ? undefined : true}
        inert={!mobileMenuOpen}
        className={`fixed inset-y-0 left-0 z-50 flex w-72 flex-col border-r border-border bg-sidebar p-6 transition-transform lg:hidden ${
          mobileMenuOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="mb-12 flex items-center justify-between">
          <Brand />
          <button
            type="button"
            onClick={closeMobileMenu}
            className="rounded-lg p-2 text-muted hover:bg-surface-hover hover:text-foreground"
            aria-label="Close navigation menu"
          >
            <span className="text-xl">×</span>
          </button>
        </div>
        <p className="mb-4 text-xs font-semibold uppercase tracking-widest text-subtle">
          Workspace
        </p>
        <Navigation onNavigate={closeMobileMenu} />
        <div className="mt-auto space-y-4 pt-6">
          <ThemeToggle className="w-full" />
          <MonitoringArea />
        </div>
      </aside>

      <section className="min-w-0 lg:ml-64">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-border px-6 py-5 lg:px-10">
          <div className="flex items-center gap-3">
            <button
              ref={menuButtonRef}
              type="button"
              onClick={() => setMobileMenuOpen(true)}
              className="rounded-lg border border-border p-2 text-muted hover:bg-surface-hover hover:text-foreground lg:hidden"
              aria-label="Open navigation menu"
              aria-controls="mobile-navigation"
              aria-expanded={mobileMenuOpen}
            >
              <span className="text-lg">☰</span>
            </button>
            <div>
              <p className="text-xs uppercase tracking-widest text-muted">
                Methane Intelligence Platform
              </p>
              <h2 className="mt-1 text-xl font-semibold">
                {pageTitle} Dashboard
              </h2>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {headerActions}
            <ThemeToggle className="lg:hidden" />
            <span className="rounded-lg border border-border px-3 py-2 text-xs text-muted">
              Chakan Zone
            </span>
          </div>
        </header>

        <div className="space-y-8 p-6 lg:p-10">
          {children}
          <footer className="border-t border-border pt-5 text-xs text-subtle">
            MethaTrace · Prototype Dashboard · Chakan Industrial Zone
          </footer>
        </div>
      </section>
    </main>
  );
}
