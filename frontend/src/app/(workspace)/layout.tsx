"use client";

import { Shell } from "@/components/shell";
import { token } from "@/lib/api";
import { ReactNode, useEffect, useState } from "react";

export default function WorkspaceLayout({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (!token()) {
      window.location.href = "/login";
      return;
    }
    setReady(true);
  }, []);
  if (!ready) return <div className="p-8 text-sm text-mist">Opening the workspace…</div>;
  return <Shell>{children}</Shell>;
}
