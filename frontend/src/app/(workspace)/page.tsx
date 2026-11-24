"use client";

import { EmptyState } from "@/components/ui";
import { api } from "@/lib/api";
import { money, percent } from "@/lib/format";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

type Dashboard = {
  total_quotation_requests: number;
  pending_drawing_analysis: number;
  awaiting_verification: number;
  completed_estimations: number;
  quotations_awaiting_approval: number;
  approved_quotations: number;
  average_processing_seconds: number | null;
  total_estimated_quotation_value: number;
  estimation_accuracy_mape: number | null;
  estimation_accuracy_sample_size: number;
  approval_rate: number | null;
  monthly_volume: { month: string; count: number }[];
  estimated_versus_actual: { part_name: string | null; estimated_cost: number; actual_cost: number }[];
  material_cost_distribution: { material: string; cost: number }[];
  process_distribution: { process: string; count: number }[];
  recent_quotations: { id: string; number: string; status: string; total_value: number | null }[];
};

export default function OverviewPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api<Dashboard>("/api/v1/dashboard").then(setData).catch((err) => setError(err.message));
  }, []);
  if (error) return <p className="text-sm text-red-700">{error}</p>;
  if (!data) return <p className="text-sm text-mist">Loading shop activity…</p>;
  const cards = [
    ["Quotation requests", String(data.total_quotation_requests)],
    ["Drawings in process", String(data.pending_drawing_analysis)],
    ["Awaiting verification", String(data.awaiting_verification)],
    ["Estimations", String(data.completed_estimations)],
    ["Awaiting approval", String(data.quotations_awaiting_approval)],
    ["Approved", String(data.approved_quotations)],
    ["Avg. processing", data.average_processing_seconds === null ? "—" : `${data.average_processing_seconds.toFixed(1)}s`],
    ["Quoted value", money(data.total_estimated_quotation_value)],
  ];
  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Overview</h1>
          <p className="text-sm text-mist">Live counts from this organization. Accuracy uses verified jobs only.</p>
        </div>
        <Link href="/quotations/new" className="rounded-md bg-navy px-4 py-2 text-sm font-semibold text-white">New quotation</Link>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map(([label, value]) => (
          <article key={label} className="rounded-lg border border-line bg-white px-4 py-3">
            <p className="text-xs uppercase tracking-wide text-mist">{label}</p>
            <p className="mt-2 text-2xl font-semibold">{value}</p>
          </article>
        ))}
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <article className="rounded-lg border border-line bg-white px-4 py-3">
          <p className="text-xs uppercase tracking-wide text-mist">Estimation accuracy (MAPE)</p>
          <p className="mt-2 text-2xl font-semibold">{data.estimation_accuracy_mape === null ? "—" : percent(data.estimation_accuracy_mape)}</p>
          <p className="text-xs text-mist">{data.estimation_accuracy_sample_size ? `${data.estimation_accuracy_sample_size} verified jobs` : "No verified historical jobs yet."}</p>
        </article>
        <article className="rounded-lg border border-line bg-white px-4 py-3">
          <p className="text-xs uppercase tracking-wide text-mist">Approval rate</p>
          <p className="mt-2 text-2xl font-semibold">{data.approval_rate === null ? "—" : percent(data.approval_rate)}</p>
          <p className="text-xs text-mist">{data.approval_rate === null ? "No approve or reject decisions yet." : "Approved, sent, or accepted divided by decided quotations."}</p>
        </article>
      </div>
      {data.total_quotation_requests === 0 ? (
        <EmptyState title="No quotations yet" body="Create a customer, upload a drawing, and verify the extracted specification. The dashboard fills from those records. It does not show sample charts." />
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          <Chart title="Monthly quotation volume" data={data.monthly_volume} x="month" y="count" />
          <Chart title="Material cost on quotation lines" data={data.material_cost_distribution} x="material" y="cost" />
          <Chart title="Process distribution" data={data.process_distribution} x="process" y="count" />
          <section className="rounded-lg border border-line bg-white p-4">
            <h2 className="text-sm font-semibold">Estimated versus actual</h2>
            {data.estimated_versus_actual.length === 0 ? <p className="mt-3 text-sm text-mist">Record an actual cost on a verified job before this comparison appears.</p> : (
              <ul className="mt-3 space-y-2 text-sm">
                {data.estimated_versus_actual.map((row) => <li key={row.part_name}>{row.part_name}: estimated {money(row.estimated_cost)}, actual {money(row.actual_cost)}</li>)}
              </ul>
            )}
          </section>
        </div>
      )}
      <section className="rounded-lg border border-line bg-white">
        <h2 className="border-b border-line px-4 py-3 text-sm font-semibold">Recent quotations</h2>
        {data.recent_quotations.length === 0 ? <p className="px-4 py-6 text-sm text-mist">Nothing has been quoted.</p> : (
          <ul>
            {data.recent_quotations.map((quote) => (
              <li key={quote.id} className="flex items-center justify-between border-b border-line px-4 py-3 text-sm last:border-0">
                <Link className="font-semibold text-accent" href={`/quotations/${quote.id}`}>{quote.number}</Link>
                <span className="text-mist">{quote.status.replaceAll("_", " ")} · {money(quote.total_value)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function Chart({ title, data, x, y }: { title: string; data: Record<string, string | number>[]; x: string; y: string }) {
  return (
    <section className="rounded-lg border border-line bg-white p-4">
      <h2 className="text-sm font-semibold">{title}</h2>
      {data.length === 0 ? <p className="mt-3 text-sm text-mist">No rows for this chart.</p> : (
        <div className="mt-4 h-56">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data}>
              <CartesianGrid stroke="#E2E8F0" vertical={false} />
              <XAxis dataKey={x} tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip />
              <Bar dataKey={y} fill="#1F4E79" radius={2} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}
