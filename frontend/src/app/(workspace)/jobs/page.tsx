"use client";

import { Badge, Button, Card, EmptyState, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";
import { money } from "@/lib/format";
import { FormEvent, useEffect, useState } from "react";

type Job = { id: string; part_name: string | null; material_name: string | null; process: string | null; quantity: number | null; estimated_cost: number | null; actual_cost: number | null; verified: boolean; training_candidate: boolean; data_origin: string };

export default function JobsPage() {
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState<Job[]>([]);
  const [similar, setSimilar] = useState<Array<{ job: Job; score: number }>>([]);
  const [clusters, setClusters] = useState<{ available: boolean; reason: string } | null>(null);
  function load(q = query) { api<Job[]>(`/api/v1/jobs?q=${encodeURIComponent(q)}`).then(setRows); }
  useEffect(() => {
    api<Job[]>("/api/v1/jobs?q=").then(setRows);
    api<{ available: boolean; reason: string }>("/api/v1/jobs/clusters").then(setClusters);
  }, []);
  async function actuals(event: FormEvent<HTMLFormElement>, id: string) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await api(`/api/v1/jobs/${id}/actuals`, { method: "POST", body: JSON.stringify({ actual_cost: Number(form.get("actual_cost")), actual_hours: form.get("actual_hours") ? Number(form.get("actual_hours")) : null, verified: form.get("verified") === "on" }) });
    load();
  }
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Historical jobs</h1>
      <form className="flex gap-2" onSubmit={(event) => { event.preventDefault(); load(); }}>
        <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search part, drawing, or material" />
        <Button type="submit">Search</Button>
      </form>
      {clusters && <p className="text-sm text-mist">{clusters.available ? "Clusters are available." : clusters.reason}</p>}
      {rows.length === 0 ? <EmptyState title="No historical jobs" body="Accept a quotation to create an operational job. It is not a training candidate until someone records an actual cost and an admin marks it." /> : rows.map((job) => (
        <Card key={job.id} title={job.part_name || "Untitled job"}>
          <p className="text-sm text-mist">{job.material_name || "—"} · {job.process || "process unset"} · qty {job.quantity ?? "—"} · origin {job.data_origin}</p>
          <p className="mt-1 text-sm">Estimated {money(job.estimated_cost)} · actual {money(job.actual_cost)} {job.verified && <Badge tone="good">verified</Badge>} {job.training_candidate && <Badge>training candidate</Badge>}</p>
          <form onSubmit={(event) => actuals(event, job.id)} className="mt-3 grid gap-2 md:grid-cols-4">
            <Field label="Actual cost"><Input name="actual_cost" type="number" step="0.01" required /></Field>
            <Field label="Actual hours"><Input name="actual_hours" type="number" step="0.01" /></Field>
            <label className="flex items-end gap-2 text-sm"><input name="verified" type="checkbox" /> Verified</label>
            <div className="flex items-end"><Button>Save actuals</Button></div>
          </form>
          <button className="mt-3 text-sm font-semibold text-accent" onClick={() => api<Array<{ job: Job; score: number }>>(`/api/v1/jobs/${job.id}/similar`).then(setSimilar)}>Find similar jobs</button>
        </Card>
      ))}
      {similar.length > 0 && <Card title="Similar feature profiles">{similar.map((item) => <p key={item.job.id} className="text-sm">{item.job.part_name} · score {item.score}</p>)}</Card>}
    </div>
  );
}
