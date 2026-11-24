"use client";

import { Banner, Card, EmptyState } from "@/components/ui";
import { api } from "@/lib/api";
import { useEffect, useState } from "react";

export default function IntelligencePage() {
  const [experiments, setExperiments] = useState<Array<{ source: string; version?: string; row_count?: number; data_origin?: string; metrics?: Record<string, { mae?: number; rmse?: number; r2?: number; mape?: number }> }>>([]);
  const [active, setActive] = useState<{ model: { limitations: string; production_ready: boolean; is_synthetic_training: boolean; metrics: Record<string, { mae?: number; r2?: number }> } | null } | null>(null);
  useEffect(() => {
    api<{ experiments: typeof experiments }>("/api/v1/ml/experiments").then((payload) => setExperiments(payload.experiments)).catch(() => undefined);
    api<{ model: { limitations: string; production_ready: boolean; is_synthetic_training: boolean; metrics: Record<string, { mae?: number; r2?: number }> } | null }>("/api/v1/ml/models/active").then(setActive).catch(() => undefined);
  }, []);
  const model = active?.model;
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">ML intelligence</h1>
      <Banner>Synthetic development metrics describe the data generator. They are not verified factory accuracy. Data drift is reported separately from prediction error.</Banner>
      {!model ? <EmptyState title="No active model" body="Train from the learning package, import the artifact, and promote it with an explicit acknowledgement. Until then, quotations use the deterministic cost engine." /> : (
        <Card title="Active model">
          <p className="text-sm">{model.limitations}</p>
          <p className="mt-2 text-sm">Production ready: {model.production_ready ? "yes" : "no"} · synthetic training: {model.is_synthetic_training ? "yes" : "no"}</p>
          {model.metrics?.total_cost && <p className="mt-2 text-sm">Holdout total cost MAE {model.metrics.total_cost.mae?.toFixed?.(2)} · R² {model.metrics.total_cost.r2?.toFixed?.(3)}</p>}
        </Card>
      )}
      <Card title="Experiments">
        {experiments.length === 0 ? <p className="text-sm text-mist">No local experiment file yet. Run the training module to create one.</p> : experiments.map((item, index) => (
          <div key={index} className="border-b border-line py-3 text-sm last:border-0">
            <p className="font-semibold">{item.version || "run"} · {item.source} · {item.data_origin}</p>
            <p className="text-mist">{item.row_count || "—"} rows {item.metrics?.total_cost ? `· total R² ${item.metrics.total_cost.r2}` : ""}</p>
          </div>
        ))}
      </Card>
    </div>
  );
}
