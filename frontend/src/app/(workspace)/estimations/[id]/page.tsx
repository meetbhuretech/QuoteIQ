"use client";

import { Banner, Card } from "@/components/ui";
import { api } from "@/lib/api";
import { money } from "@/lib/format";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

type Estimation = {
  estimation: {
    deterministic_total: number | null; deterministic_complete: boolean; ml_total: number | null; ml_is_prediction: boolean;
    disclaimer: string; fallback_reason: string | null; production_hours_deterministic: number | null; production_hours_ml: number | null;
    lead_time_days_deterministic: number | null; lead_time_days_ml: number | null; confidence_low: number | null; confidence_high: number | null;
    assumptions: string[]; explanation: { shap_or_importance?: { method?: string; top_features?: Array<{ feature: string; shap?: number; gain?: number }> } };
  };
  components: Array<{ id: string; kind: string; label: string; formula: string; amount: number | null; complete: boolean }>;
};

export default function EstimationPage() {
  const params = useParams<{ id: string }>();
  const [data, setData] = useState<Estimation | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { api<Estimation>(`/api/v1/estimation/${params.id}`).then(setData).catch((err) => setError(err.message)); }, [params.id]);
  if (!data) return <p className="text-sm text-mist">{error || "Loading estimate…"}</p>;
  const estimate = data.estimation;
  const explanation = estimate.explanation?.shap_or_importance;
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Cost estimation</h1>
      <Banner tone={estimate.ml_is_prediction ? "warn" : "info"}>{estimate.disclaimer}</Banner>
      {estimate.fallback_reason && <p className="text-sm text-mist">Fallback reason: {estimate.fallback_reason}</p>}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Deterministic calculation">
          <p className="text-2xl font-semibold">{money(estimate.deterministic_total)}</p>
          <p className="text-xs text-mist">{estimate.deterministic_complete ? "All required inputs were present." : "The total is incomplete."} Production hours {estimate.production_hours_deterministic ?? "—"}. Lead time {estimate.lead_time_days_deterministic ?? "—"} days.</p>
          <ul className="mt-4 space-y-3 text-sm">
            {data.components.filter((item) => item.kind === "deterministic").map((item) => (
              <li key={item.id}>
                <div className="flex justify-between font-medium"><span>{item.label}</span><span>{money(item.amount)}</span></div>
                <p className="text-xs text-mist">{item.formula}</p>
              </li>
            ))}
          </ul>
        </Card>
        <Card title={estimate.ml_is_prediction ? "Model advisory" : "No model prediction"}>
          {estimate.ml_is_prediction ? (
            <>
              <p className="text-2xl font-semibold">{money(estimate.ml_total)}</p>
              <p className="text-xs text-mist">Hours {estimate.production_hours_ml ?? "—"} · lead {estimate.lead_time_days_ml ?? "—"} days</p>
              {estimate.confidence_low !== null && <p className="mt-2 text-xs text-mist">Holdout MAE band {money(estimate.confidence_low)} to {money(estimate.confidence_high)}.</p>}
              <p className="mt-3 text-xs uppercase text-mist">Explanation method: {explanation?.method || "unavailable"}</p>
              <ul className="mt-2 space-y-1 text-sm">
                {(explanation?.top_features || []).map((feature) => <li key={feature.feature}>{feature.feature}: {feature.shap ?? feature.gain}</li>)}
              </ul>
            </>
          ) : <p className="text-sm text-mist">Import and promote a model before this panel shows a prediction. The deterministic total is still usable.</p>}
        </Card>
      </div>
      <Card title="Assumptions">
        <ul className="list-disc space-y-1 pl-5 text-sm">{estimate.assumptions.map((note) => <li key={note}>{note}</li>)}</ul>
      </Card>
    </div>
  );
}
