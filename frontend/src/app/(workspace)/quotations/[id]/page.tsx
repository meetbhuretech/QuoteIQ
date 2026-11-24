"use client";

import { Badge, Banner, Button, Card, ErrorText, TextArea } from "@/components/ui";
import { api } from "@/lib/api";
import { money } from "@/lib/format";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

type Detail = {
  quotation: {
    id: string; number: string; status: string; currency: string; total_value: number | null;
    validity_until: string | null; notes: string | null; assumptions: string[]; missing_information: string[];
    confidence_low: number | null; confidence_high: number | null;
  };
  customer: { name: string; company: string | null };
  items: Array<{ id: string; drawing_id: string; part_name: string | null; material: string | null; quantity: number; material_cost: number | null; machining_cost: number | null; setup_cost: number | null; finishing_cost: number | null; additional_cost: number | null; profit_amount: number | null; total: number | null; production_hours: number | null; lead_time_days: number | null; ml_total_advisory: number | null; assumptions: string[]; missing_information: string[] }>;
  approvals: Array<{ action: string; comment: string | null; created_at: string }>;
};

export default function QuotationDetailPage() {
  const params = useParams<{ id: string }>();
  const [detail, setDetail] = useState<Detail | null>(null);
  const [comment, setComment] = useState("");
  const [error, setError] = useState("");
  const [drawings, setDrawings] = useState<Array<{ id: string; original_filename: string; status: string; quotation_id: string | null }>>([]);

  function load() {
    api<Detail>(`/api/v1/quotations/${params.id}`).then(setDetail).catch((err) => setError(err.message));
    api<{ items: Array<{ id: string; original_filename: string; status: string; quotation_id: string | null }> }>("/api/v1/drawings?page_size=100").then((payload) => setDrawings(payload.items.filter((item) => item.quotation_id === params.id))).catch(() => undefined);
  }
  useEffect(load, [params.id]);

  async function act(path: string) {
    setError("");
    try {
      await api(`/api/v1/quotations/${params.id}/${path}`, { method: "POST", body: JSON.stringify({ comment }) });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed.");
    }
  }

  async function download() {
    const blob = await api<Blob>(`/api/v1/quotations/${params.id}/pdf`);
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${detail?.quotation.number || "quotation"}.pdf`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  if (!detail) return <p className="text-sm text-mist">{error || "Loading quotation…"}</p>;
  const quote = detail.quotation;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{quote.number}</h1>
          <p className="text-sm text-mist">{detail.customer.company || detail.customer.name}</p>
        </div>
        <Badge tone={quote.status === "approved" || quote.status === "accepted" ? "good" : quote.status === "rejected" ? "bad" : "warn"}>{quote.status.replaceAll("_", " ")}</Badge>
      </div>
      <Banner>The commercial total is the deterministic calculation. A model figure, when present, is advisory and is not the amount being approved.</Banner>
      {quote.missing_information.length > 0 && <Banner tone="warn">Missing before approval: {quote.missing_information.join("; ")}</Banner>}
      <div className="grid gap-4 lg:grid-cols-[1.4fr_0.8fr]">
        <Card title="Line items">
          {detail.items.length === 0 ? <p className="text-sm text-mist">No priced lines yet. Open a drawing, verify it, and run the estimate.</p> : detail.items.map((item) => (
            <div key={item.id} className="mb-4 border-b border-line pb-4 last:border-0">
              <div className="flex justify-between"><Link className="font-semibold text-accent" href={`/drawings/${item.drawing_id}`}>{item.part_name || "Untitled part"}</Link><span>{money(item.total, quote.currency)}</span></div>
              <p className="text-xs text-mist">{item.material || "Material unset"} · qty {item.quantity} · {item.production_hours ?? "—"} h · lead {item.lead_time_days ?? "—"} days</p>
              <dl className="mt-2 grid grid-cols-2 gap-1 text-sm md:grid-cols-3">
                <div>Material {money(item.material_cost)}</div>
                <div>Machining {money(item.machining_cost)}</div>
                <div>Setup {money(item.setup_cost)}</div>
                <div>Finishing {money(item.finishing_cost)}</div>
                <div>Additional {money(item.additional_cost)}</div>
                <div>Profit {money(item.profit_amount)}</div>
              </dl>
              {item.ml_total_advisory !== null && <p className="mt-2 text-xs text-amber-900">Advisory model total {money(item.ml_total_advisory)}. This is not the quotation total.</p>}
            </div>
          ))}
          <p className="text-lg font-semibold">Total {money(quote.total_value, quote.currency)}</p>
          {quote.confidence_low !== null && <p className="text-xs text-mist">Model residual band {money(quote.confidence_low)} to {money(quote.confidence_high)}. Not a commercial tolerance.</p>}
        </Card>
        <div className="space-y-4">
          <Card title="Drawings on this quote">
            <ul className="space-y-2 text-sm">
              {drawings.map((drawing) => <li key={drawing.id}><Link className="text-accent" href={`/drawings/${drawing.id}`}>{drawing.original_filename}</Link> · {drawing.status.replaceAll("_", " ")}</li>)}
              {drawings.length === 0 && <li className="text-mist">No drawings linked.</li>}
            </ul>
          </Card>
          <Card title="Approval">
            <TextArea value={comment} onChange={(event) => setComment(event.target.value)} rows={3} placeholder="Comment, required for rejection" />
            <div className="mt-3 flex flex-wrap gap-2">
              <Button onClick={() => act("approve")}>Approve</Button>
              <Button variant="danger" onClick={() => act("reject")}>Reject</Button>
              <Button variant="secondary" onClick={() => act("send")}>Mark sent</Button>
              <Button variant="secondary" onClick={() => act("accept")}>Mark accepted</Button>
              <Button variant="secondary" onClick={download}>Download PDF</Button>
            </div>
            <ErrorText>{error}</ErrorText>
            <ul className="mt-4 space-y-2 text-xs text-mist">
              {detail.approvals.map((record) => <li key={record.created_at}>{record.action}: {record.comment || "No comment"}</li>)}
            </ul>
          </Card>
        </div>
      </div>
      <Card title="Assumptions">
        <ul className="list-disc space-y-1 pl-5 text-sm">{(quote.assumptions.length ? quote.assumptions : ["Assumptions appear after estimation."]).slice(0, 8).map((note) => <li key={note}>{note}</li>)}</ul>
      </Card>
    </div>
  );
}
