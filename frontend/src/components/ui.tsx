import { cn } from "@/lib/cn";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react";

const buttonStyles = cva(
  "inline-flex items-center justify-center rounded-md text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50",
  {
    variants: {
      variant: {
        primary: "bg-navy text-white hover:bg-accent",
        secondary: "border border-line bg-white text-ink hover:bg-paper",
        danger: "bg-red-800 text-white hover:bg-red-900",
      },
      size: { md: "h-10 px-4", sm: "h-8 px-3 text-xs" },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export function Button({ className, variant, size, asChild, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof buttonStyles> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : "button";
  return <Comp className={cn(buttonStyles({ variant, size }), className)} {...props} />;
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cn("h-10 w-full rounded-md border border-line bg-white px-3 text-sm outline-none focus:border-accent", props.className)} />;
}

export function TextArea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={cn("w-full rounded-md border border-line bg-white px-3 py-2 text-sm outline-none focus:border-accent", props.className)} />;
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block space-y-1.5 text-sm">
      <span className="font-medium text-ink">{label}</span>
      {children}
    </label>
  );
}

export function Card({ title, children, action }: { title?: string; children: ReactNode; action?: ReactNode }) {
  return (
    <section className="rounded-lg border border-line bg-white">
      {title && (
        <header className="flex items-center justify-between border-b border-line px-5 py-3">
          <h2 className="text-sm font-semibold">{title}</h2>
          {action}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "warn" | "good" | "bad" }) {
  const tones = { neutral: "bg-slate-100 text-slate-700", warn: "bg-amber-50 text-amber-900", good: "bg-emerald-50 text-emerald-800", bad: "bg-red-50 text-red-800" };
  return <span className={cn("rounded px-2 py-0.5 text-xs font-semibold uppercase tracking-wide", tones[tone])}>{children}</span>;
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-lg border border-dashed border-line bg-white px-6 py-10">
      <h2 className="text-base font-semibold">{title}</h2>
      <p className="mt-2 max-w-xl text-sm leading-6 text-mist">{body}</p>
    </div>
  );
}

export function Banner({ children, tone = "warn" }: { children: ReactNode; tone?: "warn" | "info" }) {
  const tones = { warn: "border-amber-200 bg-amber-50 text-amber-950", info: "border-sky-200 bg-sky-50 text-sky-950" };
  return <div className={cn("rounded-md border px-4 py-3 text-sm leading-6", tones[tone])}>{children}</div>;
}

export function ErrorText({ children }: { children: ReactNode }) {
  if (!children) return null;
  return <p className="text-sm text-red-700">{children}</p>;
}
