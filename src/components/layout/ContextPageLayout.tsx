import type { ReactNode } from "react";
import { CheckCircle2, CircleAlert, type LucideIcon } from "lucide-react";

import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface ContextPageLayoutProps {
  header?: ReactNode;
  main: ReactNode;
  aside: ReactNode;
  className?: string;
  asideClassName?: string;
}

/**
 * Grille commune aux pages de détail et de configuration.
 * Le panneau contextuel précède le contenu sur petit écran et devient sticky
 * à droite sur les grands écrans.
 */
export function ContextPageLayout({
  header,
  main,
  aside,
  className,
  asideClassName,
}: ContextPageLayoutProps) {
  return (
    <div className={cn("mx-auto w-full max-w-[1500px] space-y-5", className)}>
      {header}
      <div className="grid grid-cols-1 items-start gap-5 xl:grid-cols-[minmax(0,1fr)_320px] 2xl:grid-cols-[minmax(0,1fr)_360px] xl:gap-6">
        <main className="min-w-0 space-y-5">{main}</main>
        <aside
          className={cn(
            "order-first min-w-0 space-y-4 xl:order-last xl:sticky xl:top-20",
            asideClassName,
          )}
        >
          {aside}
        </aside>
      </div>
    </div>
  );
}

export function ContextPanel({
  title,
  description,
  children,
  className,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Card className={cn("overflow-hidden", className)}>
      <div className="border-b border-border bg-muted/25 px-5 py-4">
        <h2 className="text-sm font-semibold text-foreground">{title}</h2>
        {description && (
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{description}</p>
        )}
      </div>
      <div className="space-y-4 p-5">{children}</div>
    </Card>
  );
}

export function ContextItem({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: ReactNode;
  icon?: LucideIcon;
}) {
  return (
    <div className="flex min-w-0 items-start gap-3">
      {Icon && (
        <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
          <Icon className="h-4 w-4" />
        </div>
      )}
      <div className="min-w-0 flex-1">
        <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </div>
        <div className="mt-0.5 break-words text-sm font-medium text-foreground">{value}</div>
      </div>
    </div>
  );
}

export function ConfigurationStatus({ label, configured }: { label: string; configured: boolean }) {
  const Icon = configured ? CheckCircle2 : CircleAlert;
  return (
    <div className="flex items-center justify-between gap-3 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span
        className={cn(
          "inline-flex items-center gap-1.5 text-xs font-medium",
          configured ? "text-success" : "text-warning",
        )}
      >
        <Icon className="h-3.5 w-3.5" />
        {configured ? "Configuré" : "À configurer"}
      </span>
    </div>
  );
}
