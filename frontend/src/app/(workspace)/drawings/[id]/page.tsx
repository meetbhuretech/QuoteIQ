"use client";

import { Badge, Banner, Button, Card, ErrorText, Field, Input } from "@/components/ui";
import { api, token } from "@/lib/api";
import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";

const stages = ["received", "validating", "preprocessing", "ocr", "geometry", "features", "specifications", "confidence", "awaiting_verification", "estimated"];

type Payload = {
  drawing: { id: string; original_filename: string; status: string; detected_format: string; error_message: string | null; stage_history: Array<{ stage: string; note: string }>; quotation_id: string | null };
  specification: null | {
    id: string; part_name: string | null; drawing_number: string | null; material: string | null; units: string | null;
    length: number | null; width: number | null; height: number | null; diameter: number | null; quantity: number | null;
    tolerances: string[]; detected_features: Array<{ type: string; note?: string; circle_entities?: number }>; missing_information: string[];
    confidence_scores: Record<string, number>; verification_status: string; confirmed_process: string | null;
  };
  evidence: Array<{ field_name: string; value_text: string; method: string; confidence: number; location: string | null; verification_status: string; source_document: string }>;
};

export default function DrawingPage() {
  const params = useParams<{ id: string }>();
  const [payload, setPayload] = useState<Payload | null>(null);
  const [materials, setMaterials] = useState<Array<{ material: { id: string; name: string } }>>([]);
  const [preview, setPreview] = useState<string>("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(() => {
    api<Payload>(`/api/v1/drawings/${params.id}`).then(setPayload).catch((err) => setError(err.message));
  }, [params.id]);
  useEffect(() => {
    load();
    api<Array<{ material: { id: string; name: string } }>>("/api/v1/materials").then(setMaterials).catch(() => undefined);
    const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    fetch(`${base}/api/v1/drawings/${params.id}/preview`, { headers: { Authorization: `Bearer ${token()}` } })
      .then((response) => (response.ok ? response.blob() : null))
      .then((blob) => { if (blob) setPreview(URL.createObjectURL(blob)); })
      .catch(() => undefined);
  }, [load, params.id]);

  async function verify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!payload?.specification) return;
    setError("");
    const form = new FormData(event.currentTarget);
    const body: Record<string, unknown> = { mark_verified: form.get("mark_verified") === "on", note: form.get("note") };
    ["part_name", "drawing_number", "units", "surface_finish", "confirmed_process", "confirmed_machine_category"].forEach((key) => { const value = form.get(key); if (value) body[key] = value; });
    ["length", "width", "height", "diameter", "quantity", "confirmed_machine_hours", "confirmed_setup_hours", "confirmed_hole_count", "confirmed_feature_count", "confirmed_finishing_hours", "confirmed_setup_complexity"].forEach((key) => {
      const value = form.get(key);
      if (value !== null && String(value) !== "") body[key] = Number(value);
    });
    if (form.get("material_id")) body.material_id = form.get("material_id");
    body.finishing_required = form.get("finishing_required") === "yes";
    try {
      await api(`/api/v1/analysis/${payload.specification.id}/verify`, { method: "PATCH", body: JSON.stringify(body) });
      setMessage("Specification saved.");
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Verification failed.");
    }
  }

  async function estimate() {
    setError("");
    try {
      const result = await api<{ estimation: { id: string } }>("/api/v1/estimation", { method: "POST", body: JSON.stringify({ drawing_id: params.id }) });
      window.location.href = `/estimations/${result.estimation.id}`;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Estimation failed.");
    }
  }

  if (!payload) return <p className="text-sm text-mist">{error || "Loading drawing…"}</p>;
  const spec = payload.specification;
  const reached = new Set((payload.drawing.stage_history || []).map((item) => item.stage));
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{payload.drawing.original_filename}</h1>
          <p className="text-sm text-mist">{payload.drawing.detected_format.toUpperCase()} · {payload.drawing.status.replaceAll("_", " ")}</p>
        </div>
        {payload.drawing.quotation_id && <Link className="text-sm font-semibold text-accent" href={`/quotations/${payload.drawing.quotation_id}`}>Back to quotation</Link>}
      </div>
      {payload.drawing.error_message && <Banner>{payload.drawing.error_message}</Banner>}
      <ol className="flex flex-wrap gap-2">
        {stages.map((stage) => <li key={stage}><Badge tone={reached.has(stage) ? "good" : "neutral"}>{stage.replaceAll("_", " ")}</Badge></li>)}
      </ol>
      <div className="grid gap-4 xl:grid-cols-2">
        <Card title="Drawing">
          {preview ? (
            // Blob previews come from an authenticated API response, so the optimizer cannot fetch them.
            // eslint-disable-next-line @next/next/no-img-element
            <img src={preview} alt="Drawing preview" className="max-h-[520px] w-full bg-paper object-contain" />
          ) : <p className="text-sm text-mist">No rendered preview. DXF files show extracted geometry instead of a picture.</p>}
          {spec && <ul className="mt-4 space-y-1 text-xs text-mist">{spec.detected_features.map((feature, index) => <li key={index}>{feature.type}{feature.circle_entities !== undefined ? ` · ${feature.circle_entities} circles, not confirmed holes` : ""}{feature.note ? ` · ${feature.note}` : ""}</li>)}</ul>}
        </Card>
        <Card title="Extracted evidence">
          {!spec ? <p className="text-sm text-mist">Analysis has not produced a specification.</p> : (
            <div className="space-y-3">
              <p className="text-sm">Verification: <Badge tone={spec.verification_status === "verified" ? "good" : "warn"}>{spec.verification_status}</Badge></p>
              {spec.missing_information.map((item) => <p key={item} className="rounded bg-amber-50 px-2 py-1 text-xs text-amber-950">{item}</p>)}
              <table className="w-full text-left text-xs">
                <tbody>
                  {payload.evidence.map((item, index) => (
                    <tr key={`${item.field_name}-${index}`} className="border-t border-line">
                      <td className="py-2 pr-2 font-semibold">{item.field_name}</td>
                      <td>{item.value_text}</td>
                      <td className="text-mist">{item.method} · {(item.confidence * 100).toFixed(0)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
      {spec && (
        <form onSubmit={verify}>
          <Card title="Engineer verification">
            <div className="grid gap-3 md:grid-cols-3">
              <Field label="Part name"><Input name="part_name" defaultValue={spec.part_name || ""} /></Field>
              <Field label="Drawing number"><Input name="drawing_number" defaultValue={spec.drawing_number || ""} /></Field>
              <Field label="Material">
                <select name="material_id" className="h-10 w-full rounded-md border border-line px-3 text-sm" defaultValue="">
                  <option value="">Select a catalog material</option>
                  {materials.map((item) => <option key={item.material.id} value={item.material.id}>{item.material.name}</option>)}
                </select>
              </Field>
              <Field label="Units"><Input name="units" defaultValue={spec.units || ""} placeholder="mm or in" /></Field>
              <Field label="Length"><Input name="length" type="number" step="0.001" defaultValue={spec.length ?? ""} /></Field>
              <Field label="Width"><Input name="width" type="number" step="0.001" defaultValue={spec.width ?? ""} /></Field>
              <Field label="Height"><Input name="height" type="number" step="0.001" defaultValue={spec.height ?? ""} /></Field>
              <Field label="Diameter"><Input name="diameter" type="number" step="0.001" defaultValue={spec.diameter ?? ""} /></Field>
              <Field label="Quantity"><Input name="quantity" type="number" defaultValue={spec.quantity ?? ""} /></Field>
              <Field label="Process">
                <select name="confirmed_process" className="h-10 w-full rounded-md border border-line px-3 text-sm" defaultValue={spec.confirmed_process || "milling"}>
                  {["milling", "turning", "drilling", "finishing"].map((process) => <option key={process}>{process}</option>)}
                </select>
              </Field>
              <Field label="Machine category"><Input name="confirmed_machine_category" placeholder="milling" defaultValue={spec.confirmed_process || ""} /></Field>
              <Field label="Machine hours / piece"><Input name="confirmed_machine_hours" type="number" step="0.01" /></Field>
              <Field label="Setup hours"><Input name="confirmed_setup_hours" type="number" step="0.01" /></Field>
              <Field label="Confirmed holes"><Input name="confirmed_hole_count" type="number" placeholder="0 if none" /></Field>
              <Field label="Feature count"><Input name="confirmed_feature_count" type="number" /></Field>
              <Field label="Finishing required">
                <select name="finishing_required" className="h-10 w-full rounded-md border border-line px-3 text-sm"><option value="no">No</option><option value="yes">Yes</option></select>
              </Field>
              <Field label="Finishing hours"><Input name="confirmed_finishing_hours" type="number" step="0.01" /></Field>
              <Field label="Note"><Input name="note" placeholder="What you changed" /></Field>
            </div>
            <label className="mt-4 flex items-center gap-2 text-sm"><input type="checkbox" name="mark_verified" /> Mark this specification verified</label>
            <div className="mt-4 flex gap-2">
              <Button type="submit">Save verification</Button>
              <Button type="button" variant="secondary" onClick={estimate}>Run estimation</Button>
            </div>
            <p className="mt-3 text-xs text-mist">{message}</p>
            <ErrorText>{error}</ErrorText>
          </Card>
        </form>
      )}
    </div>
  );
}
