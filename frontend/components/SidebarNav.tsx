"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS = [
  { href: "/", label: "Dashboard" },
  { href: "/jobs", label: "Jobs" },
  { href: "/ingest", label: "Ingest" },
  { href: "/workers", label: "Workers" },
  { href: "/meta", label: "Meta AI" },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(href + "/");
}

export default function TopNav() {
  const pathname = usePathname();
  return (
    <nav className="topnav" aria-label="Primary">
      {ITEMS.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          className={`topnav-item${isActive(pathname, item.href) ? " active" : ""}`}
          aria-current={isActive(pathname, item.href) ? "page" : undefined}
        >
          {item.label}
        </Link>
      ))}
    </nav>
  );
}
