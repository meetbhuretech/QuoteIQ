"use client";

import { Badge, EmptyState } from "@/components/ui";
import { api } from "@/lib/api";
import Link from "next/link";
import { useEffect, useState } from "react";

type Drawing = { id: string; original_filename: string; status: string; detected_format: string; byte_size: number };

export default function DrawingsPage() {
  const [rows, setRows] = useState<Drawing[]>([]);
  useEffect(() => { api<{ items: Drawing[] }>("/api/v1/drawings").then((payload) => setRows(payload.items)); }, []);
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Drawing analysis</h1>
      {rows.length === 0 ? <EmptyState title="No drawings" body="Upload a PDF, DXF, or image from a new quotation. Analysis stops for human verification and does not guess a manufacturing process." /> : (
        <div className="overflow-hidden rounded-lg border border-line bg-white">
          <table className="w-full text-left text-sm">
            <thead className="bg-paper text-xs uppercase text-mist"><tr><th className="px-4 py-3">File</th><th>Format</th><th>Status</th><th>Size</th></tr></thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="border-t border-line">
                  <td className="px-4 py-3"><Link className="font-semibold text-accent" href={`/drawings/${row.id}`}>{row.original_filename}</Link></td>
                  <td>{row.detected_format}</td>
                  <td><Badge tone={row.status === "failed" ? "bad" : row.status === "estimated" ? "good" : "warn"}>{row.status.replaceAll("_", " ")}</Badge></td>
                  <td className="text-mist">{Math.ceil(row.byte_size / 1024)} KB</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
