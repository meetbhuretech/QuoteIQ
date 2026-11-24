"use client";

import { Button, Card, EmptyState, ErrorText, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";
import { FormEvent, useEffect, useState } from "react";

type Customer = { id: string; name: string; company: string | null; email: string | null; phone: string | null };

export default function CustomersPage() {
  const [rows, setRows] = useState<Customer[]>([]);
  const [error, setError] = useState("");
  function load() { api<{ items: Customer[] }>("/api/v1/customers").then((payload) => setRows(payload.items)).catch((err) => setError(err.message)); }
  useEffect(load, []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await api("/api/v1/customers", { method: "POST", body: JSON.stringify({ name: form.get("name"), company: form.get("company") || null, email: form.get("email") || null, phone: form.get("phone") || null }) });
      event.currentTarget.reset();
      load();
    } catch (err) { setError(err instanceof Error ? err.message : "Could not add the customer."); }
  }
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
      <div>
        <h1 className="mb-4 text-2xl font-semibold">Customers</h1>
        {rows.length === 0 ? <EmptyState title="No customers" body="Customers belong to this organization only. Another shop cannot see them." /> : (
          <div className="overflow-hidden rounded-lg border border-line bg-white">
            <table className="w-full text-left text-sm"><thead className="bg-paper text-xs uppercase text-mist"><tr><th className="px-4 py-3">Name</th><th>Company</th><th>Email</th></tr></thead>
              <tbody>{rows.map((row) => <tr key={row.id} className="border-t border-line"><td className="px-4 py-3 font-medium">{row.name}</td><td>{row.company || "—"}</td><td>{row.email || "—"}</td></tr>)}</tbody>
            </table>
          </div>
        )}
      </div>
      <Card title="Add customer">
        <form onSubmit={submit} className="space-y-3">
          <Field label="Name"><Input name="name" required /></Field>
          <Field label="Company"><Input name="company" /></Field>
          <Field label="Email"><Input name="email" type="email" /></Field>
          <Field label="Phone"><Input name="phone" /></Field>
          <ErrorText>{error}</ErrorText>
          <Button>Save customer</Button>
        </form>
      </Card>
    </div>
  );
}
