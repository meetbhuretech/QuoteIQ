"use client";

import { Badge, Banner, Button, Card, ErrorText } from "@/components/ui";
import { api } from "@/lib/api";
import { useEffect, useState } from "react";

type Model = { id: string; version: string; stage: string; algorithm: string; is_synthetic_training: boolean; production_ready: boolean; limitations: string; metrics: Record<string, { r2?: number; mae?: number }> };

export default function ModelsPage() {
  const [rows, setRows] = useState<Model[]>([]);
  const [error, setError] = useState("");
  const [ack, setAck] = useState(false);
  function load() { api<Model[]>("/api/v1/ml/models").then(setRows).catch((err) => setError(err.message)); }
  useEffect(load, []);
  async function run(path: string, body?: object) {
    setError("");
    try { await api(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }); load(); }
    catch (err) { setError(err instanceof Error ? err.message : "Model action failed."); }
  }
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Model registry</h1>
        <Button onClick={() => run("/api/v1/ml/models/import-local")}>Import local candidate</Button>
      </div>
      <Banner>Promotion requires the quality gates and, for synthetic models, an acknowledgement. Passing the gates does not certify a model for production. Rollback only points at an already registered version.</Banner>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={ack} onChange={(event) => setAck(event.target.checked)} /> I understand this candidate was not trained on verified factory jobs, if it is synthetic.</label>
      <ErrorText>{error}</ErrorText>
      {rows.map((model) => (
        <Card key={model.id} title={`${model.version} · ${model.algorithm}`}>
          <div className="flex gap-2"><Badge tone={model.stage === "active" ? "good" : "warn"}>{model.stage}</Badge>{model.production_ready ? <Badge tone="good">production ready</Badge> : <Badge tone="warn">not production ready</Badge>}</div>
          <p className="mt-3 text-sm">{model.limitations}</p>
          {model.metrics?.total_cost && <p className="mt-2 text-sm text-mist">Total cost holdout R² {model.metrics.total_cost.r2} · MAE {model.metrics.total_cost.mae}</p>}
          <div className="mt-3 flex gap-2">
            <Button onClick={() => run(`/api/v1/ml/models/${model.id}/promote`, { acknowledge_limitations: ack })}>Promote</Button>
            <Button variant="secondary" onClick={() => run(`/api/v1/ml/models/${model.id}/rollback`)}>Roll back to this version</Button>
          </div>
        </Card>
      ))}
    </div>
  );
}
