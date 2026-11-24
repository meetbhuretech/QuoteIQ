"use client";

import { Button, ErrorText, Field, Input } from "@/components/ui";
import { api, saveSession, type Session } from "@/lib/api";
import Link from "next/link";
import { FormEvent, useState } from "react";

export default function LoginPage() {
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      const session = await api<Session>("/api/v1/auth/login", { method: "POST", body: JSON.stringify({ email: form.get("email"), password: form.get("password") }) });
      saveSession(session);
      window.location.href = "/";
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="grid min-h-screen md:grid-cols-2">
      <section className="hidden bg-navy px-12 py-16 text-white md:block">
        <p className="text-sm uppercase tracking-[0.2em] text-slate-400">QuoteIQ</p>
        <h1 className="mt-6 max-w-md text-4xl font-semibold leading-tight">Quotations that show their evidence.</h1>
        <p className="mt-4 max-w-md text-slate-300">Upload a drawing, confirm what was actually extracted, and price it from your shop rates. Model estimates stay advisory.</p>
      </section>
      <section className="flex items-center justify-center px-6">
        <form onSubmit={submit} className="w-full max-w-sm space-y-4">
          <h2 className="text-2xl font-semibold">Sign in</h2>
          <Field label="Email"><Input name="email" type="email" required /></Field>
          <Field label="Password"><Input name="password" type="password" required /></Field>
          <ErrorText>{error}</ErrorText>
          <Button className="w-full" disabled={pending}>{pending ? "Signing in…" : "Sign in"}</Button>
          <p className="text-sm text-mist">New shop? <Link className="font-semibold text-accent" href="/register">Create an organization</Link></p>
        </form>
      </section>
    </div>
  );
}
