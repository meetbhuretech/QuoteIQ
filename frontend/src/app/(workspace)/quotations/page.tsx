"use client";

import { Badge, EmptyState } from "@/components/ui";
import { api } from "@/lib/api";
import { money } from "@/lib/format";
import Link from "next/link";
import { useEffect, useState } from "react";

type Quote = { id: string; number: string; status: string; total_value: number | null; currency: string; validity_until: string | null };

export default function QuotationsPage() {
  const [rows, setRows] = useState<Quote[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    api<{ items: Quote[] }>("/api/v1/quotations").then((payload) => setRows(payload.items)).catch((err) => setError(err.message));
  }, []);
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Quotations</h1>
        <Link href="/quotations/new" className="rounded-md bg-navy px-4 py-2 text-sm font-semibold text-white">New quotation</Link>
      </div>
      {error && <p className="text-sm text-red-700">{error}</p>}
      {rows.length === 0 ? <EmptyState title="No quotations" body="A quotation starts with a customer and one or more drawings. Approval is a separate step from estimation." /> : (
        <div className="overflow-hidden rounded-lg border border-line bg-white">
          <table className="w-full text-left text-sm">
            <thead className="bg-paper text-xs uppercase tracking-wide text-mist"><tr><th className="px-4 py-3">Number</th><th>Status</th><th>Total</th><th>Valid until</th></tr></thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="border-t border-line">
                  <td className="px-4 py-3"><Link className="font-semibold text-accent" href={`/quotations/${row.id}`}>{row.number}</Link></td>
                  <td><Badge>{row.status.replaceAll("_", " ")}</Badge></td>
                  <td>{money(row.total_value, row.currency)}</td>
                  <td className="text-mist">{row.validity_until || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
