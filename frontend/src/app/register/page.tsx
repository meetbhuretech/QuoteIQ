"use client";

import { Button, ErrorText, Field, Input } from "@/components/ui";
import { api, saveSession, type Session } from "@/lib/api";
import Link from "next/link";
import { FormEvent, useState } from "react";

export default function RegisterPage() {
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      const session = await api<Session>("/api/v1/auth/register", {
        method: "POST",
        body: JSON.stringify({
          email: form.get("email"),
          password: form.get("password"),
          full_name: form.get("full_name"),
          organization_name: form.get("organization_name"),
        }),
      });
      saveSession(session);
      window.location.href = "/";
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed.");
    }
  }
  return (
    <div className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6">
      <h1 className="text-2xl font-semibold">Create your shop</h1>
      <p className="mt-2 text-sm text-mist">You become the organization admin. Sample materials and rates are added so you can replace them.</p>
      <form onSubmit={submit} className="mt-6 space-y-4">
        <Field label="Your name"><Input name="full_name" required /></Field>
        <Field label="Organization"><Input name="organization_name" required /></Field>
        <Field label="Email"><Input name="email" type="email" required /></Field>
        <Field label="Password"><Input name="password" type="password" required minLength={10} /></Field>
        <ErrorText>{error}</ErrorText>
        <Button className="w-full">Create organization</Button>
      </form>
      <p className="mt-4 text-sm text-mist">Already registered? <Link className="font-semibold text-accent" href="/login">Sign in</Link></p>
    </div>
  );
}
