"use client";

import { api, clearSession } from "@/lib/api";
import { cn } from "@/lib/cn";
import { Boxes, Cpu, Factory, FileSearch, LayoutDashboard, Library, Receipt, Settings, Users } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode } from "react";

const links = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/quotations", label: "Quotations", icon: Receipt },
  { href: "/drawings", label: "Drawing Analysis", icon: FileSearch },
  { href: "/customers", label: "Customers", icon: Users },
  { href: "/materials", label: "Materials & Pricing", icon: Boxes },
  { href: "/jobs", label: "Historical Jobs", icon: Library },
  { href: "/ml", label: "ML Intelligence", icon: Cpu },
  { href: "/models", label: "Model Registry", icon: Factory },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const organization = typeof window !== "undefined" ? localStorage.getItem("quoteiq_org") : "";
  const name = typeof window !== "undefined" ? localStorage.getItem("quoteiq_name") : "";
  const role = typeof window !== "undefined" ? localStorage.getItem("quoteiq_role") : "";

  async function logout() {
    try {
      await api("/api/v1/auth/logout", { method: "POST" });
    } catch {
      /* The token is discarded locally either way. */
    }
    clearSession();
    window.location.href = "/login";
  }

  return (
    <div className="min-h-screen md:grid md:grid-cols-[240px_1fr]">
      <aside className="bg-navy text-slate-200">
        <div className="border-b border-white/10 px-5 py-5">
          <p className="text-lg font-semibold tracking-tight text-white">QuoteIQ</p>
          <p className="mt-1 text-xs text-slate-400">Manufacturing quotations</p>
        </div>
        <nav className="space-y-1 px-3 py-4">
          {links.map((link) => {
            const active = pathname === link.href || (link.href !== "/" && pathname.startsWith(link.href));
            const Icon = link.icon;
            return (
              <Link key={link.href} href={link.href} className={cn("flex items-center gap-2 rounded-md px-3 py-2 text-sm", active ? "bg-white/10 text-white" : "text-slate-300 hover:bg-white/5")}>
                <Icon size={16} />
                {link.label}
              </Link>
            );
          })}
        </nav>
      </aside>
      <div>
        <header className="flex items-center justify-between border-b border-line bg-white px-6 py-3">
          <div>
            <p className="text-sm font-semibold">{organization || "Organization"}</p>
            <p className="text-xs text-mist">{name} · {role?.replaceAll("_", " ")}</p>
          </div>
          <button onClick={logout} className="text-sm font-medium text-accent">Log out</button>
        </header>
        <main className="px-6 py-6">{children}</main>
      </div>
    </div>
  );
}
