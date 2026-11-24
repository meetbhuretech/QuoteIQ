"use client";

import { Banner, Button, Card, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";
import { money } from "@/lib/format";
import { FormEvent, useEffect, useState } from "react";

type Row = { material: { id: string; name: string; category: string; density: number; notes: string | null; availability: string }; current_price: { unit_price: number; currency: string; supplier: string | null; notes: string | null } | null };

export default function MaterialsPage() {
  const [rows, setRows] = useState<Row[]>([]);
  const [message, setMessage] = useState("");
  function load() { api<Row[]>("/api/v1/materials").then(setRows); }
  useEffect(load, []);
  async function updatePrice(event: FormEvent<HTMLFormElement>, id: string) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await api(`/api/v1/materials/${id}`, { method: "PATCH", body: JSON.stringify({ unit_price: Number(form.get("unit_price")), supplier: form.get("supplier") || null }) });
    setMessage("A new price row was stored. Older prices remain as history.");
    load();
  }
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Materials and pricing</h1>
      <Banner>Prices live in the material catalog. The model does not contain a hardcoded supplier price. Sample rows are marked and should be replaced.</Banner>
      {message && <p className="text-sm text-mist">{message}</p>}
      <div className="grid gap-3">
        {rows.map((row) => (
          <Card key={row.material.id} title={`${row.material.name} · ${row.material.category}`}>
            <p className="text-sm text-mist">Density {row.material.density} g/cm³ · {row.material.availability} · current {money(row.current_price?.unit_price, row.current_price?.currency || "USD")} / kg</p>
            <p className="mt-1 text-xs text-mist">{row.material.notes}</p>
            <form onSubmit={(event) => updatePrice(event, row.material.id)} className="mt-3 grid gap-3 md:grid-cols-[1fr_1fr_auto]">
              <Field label="New unit price"><Input name="unit_price" type="number" step="0.01" required defaultValue={row.current_price?.unit_price} /></Field>
              <Field label="Supplier"><Input name="supplier" defaultValue={row.current_price?.supplier || ""} /></Field>
              <div className="flex items-end"><Button>Update price</Button></div>
            </form>
          </Card>
        ))}
      </div>
    </div>
  );
}
