"use client";

import { Button, Card, ErrorText, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";
import { FormEvent, useEffect, useState } from "react";

type Settings = {
  cost_settings: { currency: string; scrap_allowance_pct: number; overhead_pct: number; profit_margin_pct: number; labor_hourly_rate: number; tooling_cost: number; packaging_cost: number; shipping_cost: number; stock_fill_ratio: number; hours_per_day: number; shipping_days: number; default_validity_days: number };
  processes: Array<{ id: string; name: string; category: string; description: string | null }>;
  rates: Array<{ process_id: string | null; hourly_rate: number; setup_hourly_rate: number; effective_date: string }>;
};

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  function load() { api<Settings>("/api/v1/settings").then(setSettings).catch((err) => setError(err.message)); }
  useEffect(load, []);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body = Object.fromEntries(Array.from(form.entries()).map(([key, value]) => [key, Number(value)]));
    try { await api("/api/v1/settings", { method: "PUT", body: JSON.stringify(body) }); setSaved("Cost settings saved."); load(); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not save settings."); }
  }
  async function rate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await api("/api/v1/settings/rates", { method: "POST", body: JSON.stringify({ process_category: form.get("process_category"), hourly_rate: Number(form.get("hourly_rate")), setup_hourly_rate: Number(form.get("setup_hourly_rate")) }) });
      setSaved("A new rate row is now the latest rate for that process.");
      load();
    } catch (err) { setError(err instanceof Error ? err.message : "Could not save the rate."); }
  }
  if (!settings) return <p className="text-sm text-mist">{error || "Loading settings…"}</p>;
  const cost = settings.cost_settings;
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Settings</h1>
      <form onSubmit={save}>
        <Card title="Cost formula inputs">
          <div className="grid gap-3 md:grid-cols-3">
            {([
              ["scrap_allowance_pct", cost.scrap_allowance_pct],
              ["overhead_pct", cost.overhead_pct],
              ["profit_margin_pct", cost.profit_margin_pct],
              ["labor_hourly_rate", cost.labor_hourly_rate],
              ["tooling_cost", cost.tooling_cost],
              ["packaging_cost", cost.packaging_cost],
              ["shipping_cost", cost.shipping_cost],
              ["stock_fill_ratio", cost.stock_fill_ratio],
              ["hours_per_day", cost.hours_per_day],
              ["shipping_days", cost.shipping_days],
              ["default_validity_days", cost.default_validity_days],
            ] as Array<[string, number]>).map(([name, value]) => <Field key={name} label={name.replaceAll("_", " ")}><Input name={name} type="number" step="0.01" defaultValue={value} /></Field>)}
          </div>
          <Button className="mt-4">Save settings</Button>
        </Card>
      </form>
      <Card title="Process rates">
        <ul className="mb-4 space-y-2 text-sm">{settings.processes.map((process) => <li key={process.id}><span className="font-semibold">{process.name}</span> · {process.description}</li>)}</ul>
        <form onSubmit={rate} className="grid gap-3 md:grid-cols-4">
          <Field label="Process"><select name="process_category" className="h-10 rounded-md border border-line px-3 text-sm">{settings.processes.map((process) => <option key={process.category} value={process.category}>{process.name}</option>)}</select></Field>
          <Field label="Hourly rate"><Input name="hourly_rate" type="number" step="0.01" required /></Field>
          <Field label="Setup hourly rate"><Input name="setup_hourly_rate" type="number" step="0.01" required /></Field>
          <div className="flex items-end"><Button>Add rate</Button></div>
        </form>
        <p className="mt-3 text-xs text-mist">{saved}</p>
        <ErrorText>{error}</ErrorText>
      </Card>
    </div>
  );
}
