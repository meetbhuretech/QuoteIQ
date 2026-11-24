"use client";

import { Button, Card, ErrorText, Field, Input, TextArea } from "@/components/ui";
import { api } from "@/lib/api";
import { FormEvent, useEffect, useState } from "react";

type Customer = { id: string; name: string; company: string | null };

export default function NewQuotationPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    api<{ items: Customer[] }>("/api/v1/customers").then((payload) => setCustomers(payload.items)).catch((err) => setError(err.message));
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setStatus("Creating the quotation…");
    const form = new FormData(event.currentTarget);
    try {
      let customerId = String(form.get("customer_id") || "");
      if (!customerId && !form.get("customer_name")) throw new Error("Select a customer or enter a new customer name.");
      if (!customerId) {
        const created = await api<Customer>("/api/v1/customers", {
          method: "POST",
          body: JSON.stringify({ name: form.get("customer_name"), company: form.get("company") || null }),
        });
        customerId = created.id;
      }
      const quotation = await api<{ quotation: { id: string } }>("/api/v1/quotations", {
        method: "POST",
        body: JSON.stringify({ customer_id: customerId, notes: form.get("notes") || null }),
      });
      const files = (form.getAll("drawings") as File[]).filter((file) => file.size > 0);
      for (const file of files) {
        const body = new FormData();
        body.set("file", file);
        body.set("customer_id", customerId);
        body.set("quotation_id", quotation.quotation.id);
        setStatus(`Uploading ${file.name}…`);
        await api(`/api/v1/drawings/upload`, { method: "POST", body, form: true });
      }
      window.location.href = `/quotations/${quotation.quotation.id}`;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the quotation.");
      setStatus("");
    }
  }

  return (
    <form onSubmit={submit} className="mx-auto max-w-3xl space-y-4">
      <h1 className="text-2xl font-semibold">New quotation</h1>
      <p className="text-sm text-mist">The drawing is stored and analysed after upload. Nothing is priced until an engineer verifies the specification.</p>
      <Card title="Customer">
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Existing customer">
            <select name="customer_id" className="h-10 w-full rounded-md border border-line bg-white px-3 text-sm">
              <option value="">Create a new customer instead</option>
              {customers.map((customer) => <option key={customer.id} value={customer.id}>{customer.company || customer.name}</option>)}
            </select>
          </Field>
          <Field label="New customer name"><Input name="customer_name" placeholder="Only if no customer is selected" /></Field>
          <Field label="Company"><Input name="company" /></Field>
          <Field label="Notes"><TextArea name="notes" rows={3} /></Field>
        </div>
      </Card>
      <Card title="Drawings">
        <Field label="PDF, DXF, PNG, or JPEG">
          <Input name="drawings" type="file" accept=".pdf,.dxf,.png,.jpg,.jpeg" multiple required />
        </Field>
        <p className="mt-2 text-xs text-mist">Maximum 25 MB each. Several drawings can belong to the same quotation.</p>
      </Card>
      <ErrorText>{error}</ErrorText>
      {status && <p className="text-sm text-mist">{status}</p>}
      <Button>Create and analyse</Button>
    </form>
  );
}
