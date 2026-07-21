import { createFileRoute, Link } from "@tanstack/react-router";
import {
  ArrowLeft,
  CalendarClock,
  History,
  MapPin,
  Phone,
  Route as RouteIcon,
  ShieldCheck,
  User,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import {
  ContextItem,
  ContextPageLayout,
  ContextPanel,
} from "@/components/layout/ContextPageLayout";
import { TimeRemainingBadge } from "@/components/TimeRemainingBadge";
import { CallStatusBadge, StageBadge } from "@/components/StatusBadge";
import { ErrorState } from "@/components/ErrorState";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDateTime, formatDuration } from "@/lib/time";
import { useDossier, useDossierCalls, useSettings, useUpdateDossierM2s } from "@/lib/hooks";
import type { Dossier } from "@/data/types";

export const Route = createFileRoute("/dossiers/$id")({
  component: DossierDetail,
  head: () => ({ meta: [{ title: "Dossier · Nida'a M2S" }] }),
});

interface M2sEditForm {
  assure: string;
  vehicule: string;
  matricule: string;
  adresse: string;
  zoneDossier: string;
  dateSinistre: string;
  nomAssurance: string;
  numTelClient: string;
}

const EMPTY_M2S_FORM: M2sEditForm = {
  assure: "",
  vehicule: "",
  matricule: "",
  adresse: "",
  zoneDossier: "",
  dateSinistre: "",
  nomAssurance: "",
  numTelClient: "",
};

function toLocalDateTimeInput(date: Date | null): string {
  if (!date || Number.isNaN(date.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function m2sFormFromDossier(dossier: Dossier): M2sEditForm {
  return {
    assure: dossier.assure ?? "",
    vehicule: dossier.vehicule ?? "",
    matricule: dossier.matricule ?? "",
    adresse: dossier.adresse ?? "",
    zoneDossier: dossier.zoneDossier ?? "",
    dateSinistre: toLocalDateTimeInput(dossier.dateSinistre),
    nomAssurance: dossier.nomAssurance ?? "",
    numTelClient: dossier.numTelClient ?? "",
  };
}

function displayValue(value: string | null | undefined): string {
  return value?.trim() || "—";
}

function formatDateSinistre(date: Date | null): string {
  if (!date || Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("fr-FR", {
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(date);
}

function InfoItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="space-y-1">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-sm font-medium text-foreground break-words">{value}</div>
    </div>
  );
}

function EditField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-sm font-medium">{label}</Label>
      {children}
    </div>
  );
}

function DossierDetail() {
  const { id } = Route.useParams();
  const dossierQ = useDossier(id);
  const callsQ = useDossierCalls(id);
  const settingsQ = useSettings();
  const updateM2s = useUpdateDossierM2s();
  const [editOpen, setEditOpen] = useState(false);
  const [editForm, setEditForm] = useState<M2sEditForm>(EMPTY_M2S_FORM);

  if (dossierQ.isLoading && !dossierQ.data) {
    return (
      <ContextPageLayout
        header={<Skeleton className="h-8 w-full max-w-xl" />}
        main={
          <>
            <Skeleton className="h-40 w-full" />
            <Skeleton className="h-56 w-full" />
          </>
        }
        aside={<Skeleton className="h-80 w-full" />}
      />
    );
  }
  if (dossierQ.isError || !dossierQ.data) {
    return <ErrorState onRetry={() => dossierQ.refetch()} />;
  }
  const dossier = dossierQ.data;
  const calls = callsQ.data ?? [];
  const latestCall = calls.at(-1);
  const nextAction =
    dossier.status === "valide"
      ? "Aucune relance à prévoir"
      : dossier.handoffReason
        ? "Traitement par le superviseur"
        : "Prochaine relance selon le seuil SLA";

  return (
    <ContextPageLayout
      header={
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <Link
            to="/"
            className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" /> Retour au tableau de bord
          </Link>
          <div className="flex max-w-xl items-start gap-2 rounded-lg border border-primary/20 bg-primary/5 px-3 py-2">
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
            <p className="text-xs leading-relaxed text-muted-foreground">
              <span className="font-medium text-foreground">Statut piloté par M2S</span>
              {" — "}validation effectuée par le constateur dans la plateforme M2S.
            </p>
          </div>
        </div>
      }
      main={
        <>
          <Card className="p-6">
            <div className="flex flex-wrap items-start justify-between gap-5">
              <div className="min-w-0">
                <div className="text-xs uppercase tracking-wide text-muted-foreground">
                  Réf. sinistre
                </div>
                <div className="mt-1 break-all font-mono text-2xl font-bold">{dossier.refM2s}</div>
                <div className="mt-3 text-sm text-muted-foreground">
                  <span className="font-medium text-foreground">
                    {displayValue(dossier.assure)}
                  </span>
                  {dossier.vehicule && ` · ${dossier.vehicule}`}
                  {dossier.matricule && ` · ${dossier.matricule}`}
                </div>
              </div>
              <span
                className={
                  dossier.status === "valide"
                    ? "inline-flex rounded-full bg-success/10 px-3 py-1 text-xs font-semibold text-success"
                    : "inline-flex rounded-full bg-warning/10 px-3 py-1 text-xs font-semibold text-warning"
                }
              >
                {dossier.status === "valide" ? "Dossier validé" : "Dossier en retard"}
              </span>
            </div>

            <div className="mt-6 border-t border-border pt-5">
              <div className="mb-4 flex items-center gap-2">
                <RouteIcon className="h-4 w-4 text-primary" />
                <h2 className="text-sm font-semibold text-foreground">Suivi opérationnel</h2>
              </div>
              <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 2xl:grid-cols-4">
                <ContextItem
                  label="Étape actuelle"
                  value={
                    <StageBadge
                      stage={dossier.currentStage}
                      handoffReason={dossier.handoffReason}
                      nbRelancesIa={settingsQ.data?.nbRelancesIa}
                    />
                  }
                />
                <ContextItem
                  label="Appels réalisés"
                  value={`${calls.length} appel${calls.length > 1 ? "s" : ""}`}
                />
                <ContextItem
                  label="Dernier résultat"
                  value={
                    latestCall ? (
                      <div className="flex flex-wrap items-center gap-2">
                        <CallStatusBadge status={latestCall.status} />
                        <span className="text-xs font-normal text-muted-foreground">
                          {formatDateTime(latestCall.startedAt)}
                        </span>
                      </div>
                    ) : (
                      "Aucun appel"
                    )
                  }
                />
                <ContextItem label="Prochaine action" value={nextAction} />
              </div>
            </div>
          </Card>

          <Card className="p-6 space-y-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-base font-semibold">Informations complémentaires</h2>
                <p className="text-sm text-muted-foreground">Données métier transmises par M2S.</p>
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  setEditForm(m2sFormFromDossier(dossier));
                  setEditOpen(true);
                }}
              >
                Modifier
              </Button>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-5">
              <InfoItem label="Assuré" value={displayValue(dossier.assure)} />
              <InfoItem label="Véhicule" value={displayValue(dossier.vehicule)} />
              <InfoItem label="Matricule" value={displayValue(dossier.matricule)} />
              <InfoItem label="Lieu du sinistre" value={displayValue(dossier.adresse)} />
              <InfoItem label="Zone" value={displayValue(dossier.zoneDossier)} />
              <InfoItem label="Date du sinistre" value={formatDateSinistre(dossier.dateSinistre)} />
              <InfoItem label="Assurance" value={displayValue(dossier.nomAssurance)} />
              <InfoItem label="Téléphone client" value={displayValue(dossier.numTelClient)} />
            </div>
          </Card>

          <Dialog open={editOpen} onOpenChange={setEditOpen}>
            <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>Modifier les informations du sinistre</DialogTitle>
              </DialogHeader>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 py-2">
                <EditField label="Assuré">
                  <Input
                    value={editForm.assure}
                    onChange={(e) => setEditForm((f) => ({ ...f, assure: e.target.value }))}
                  />
                </EditField>
                <EditField label="Véhicule">
                  <Input
                    value={editForm.vehicule}
                    onChange={(e) => setEditForm((f) => ({ ...f, vehicule: e.target.value }))}
                  />
                </EditField>
                <EditField label="Matricule">
                  <Input
                    value={editForm.matricule}
                    onChange={(e) => setEditForm((f) => ({ ...f, matricule: e.target.value }))}
                  />
                </EditField>
                <EditField label="Date du sinistre">
                  <Input
                    type="datetime-local"
                    value={editForm.dateSinistre}
                    onChange={(e) => setEditForm((f) => ({ ...f, dateSinistre: e.target.value }))}
                  />
                </EditField>
                <EditField label="Assurance">
                  <Input
                    value={editForm.nomAssurance}
                    onChange={(e) => setEditForm((f) => ({ ...f, nomAssurance: e.target.value }))}
                  />
                </EditField>
                <EditField label="Téléphone client">
                  <Input
                    value={editForm.numTelClient}
                    onChange={(e) => setEditForm((f) => ({ ...f, numTelClient: e.target.value }))}
                  />
                </EditField>
                <div className="sm:col-span-2">
                  <EditField label="Lieu du sinistre">
                    <Input
                      value={editForm.adresse}
                      onChange={(e) => setEditForm((f) => ({ ...f, adresse: e.target.value }))}
                    />
                  </EditField>
                </div>
                <EditField label="Zone">
                  <Input
                    value={editForm.zoneDossier}
                    onChange={(e) => setEditForm((f) => ({ ...f, zoneDossier: e.target.value }))}
                  />
                </EditField>
              </div>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setEditOpen(false)}>
                  Annuler
                </Button>
                <Button
                  type="button"
                  disabled={updateM2s.isPending}
                  onClick={() => {
                    const parsedDate = editForm.dateSinistre
                      ? new Date(editForm.dateSinistre)
                      : null;
                    updateM2s.mutate(
                      {
                        id,
                        values: {
                          assure: editForm.assure,
                          vehicule: editForm.vehicule,
                          matricule: editForm.matricule,
                          adresse: editForm.adresse,
                          zoneDossier: editForm.zoneDossier,
                          dateSinistre:
                            parsedDate && !Number.isNaN(parsedDate.getTime()) ? parsedDate : null,
                          nomAssurance: editForm.nomAssurance,
                          numTelClient: editForm.numTelClient,
                        },
                      },
                      {
                        onSuccess: () => {
                          toast.success("Informations du dossier mises à jour");
                          setEditOpen(false);
                        },
                        onError: (error) =>
                          toast.error(
                            error instanceof Error ? error.message : "Mise à jour impossible",
                          ),
                      },
                    );
                  }}
                >
                  Enregistrer
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          <div>
            <h2 className="text-sm font-semibold text-foreground mb-3 uppercase tracking-wide">
              Frise des appels ({calls.length})
            </h2>
            {callsQ.isLoading && !callsQ.data ? (
              <Skeleton className="h-32 w-full" />
            ) : calls.length === 0 ? (
              <Card className="p-8 text-center text-muted-foreground text-sm">
                Aucun appel n'a encore été passé sur ce dossier.
              </Card>
            ) : (
              <ol className="relative border-l border-border ml-3 space-y-4 pl-6">
                {calls.map((call) => (
                  <li key={call.id} className="relative">
                    <span className="absolute -left-[31px] top-3 h-3 w-3 rounded-full bg-accent ring-4 ring-background" />
                    <Link to="/appels/$id" params={{ id: call.id }} className="block">
                      <Card className="p-4 hover:bg-muted/40 transition-colors">
                        <div className="flex items-center justify-between gap-4 flex-wrap">
                          <div className="flex items-center gap-3">
                            <div className="text-sm font-medium text-foreground">
                              {formatDateTime(call.startedAt)}
                            </div>
                            <span className="text-xs text-muted-foreground">
                              Étape {call.stage} · Tentative {call.attemptNo}
                            </span>
                          </div>
                          <div className="flex items-center gap-3">
                            <span className="text-xs text-muted-foreground tabular-nums">
                              {formatDuration(call.durationSec)}
                            </span>
                            <CallStatusBadge status={call.status} />
                          </div>
                        </div>
                        {call.delayReason && (
                          <div className="mt-3 text-sm text-muted-foreground italic border-l-2 border-accent/30 pl-3">
                            « {call.delayReason} »
                          </div>
                        )}
                      </Card>
                    </Link>
                  </li>
                ))}
              </ol>
            )}
          </div>
        </>
      }
      aside={
        <>
          <ContextPanel
            title="Priorité SLA"
            description="Le délai reste visible pendant toute la consultation."
          >
            <div className="rounded-xl bg-muted/35 px-4 py-5 text-center">
              <div className="mb-3 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                {dossier.status === "valide" ? "Validation enregistrée" : "Temps restant"}
              </div>
              {dossier.status === "valide" ? (
                <div className="text-sm font-semibold text-success">
                  {dossier.validatedAt ? formatDateTime(dossier.validatedAt) : "Validé par M2S"}
                </div>
              ) : (
                <TimeRemainingBadge
                  deadline={dossier.deadlineAt}
                  remainingMinutes={dossier.remainingMinutes}
                  size="xl"
                />
              )}
            </div>
            <ContextItem
              icon={History}
              label="Dossier reçu"
              value={formatDateTime(dossier.arrivalAt)}
            />
            <ContextItem
              icon={CalendarClock}
              label="Deadline"
              value={formatDateTime(dossier.deadlineAt)}
            />
          </ContextPanel>

          <ContextPanel title="Constateur affecté">
            <div className="flex min-w-0 items-start gap-3">
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                <User className="h-5 w-5" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="break-words text-sm font-semibold text-foreground">
                  {dossier.constateur.nom}
                </div>
                <div className="mt-1.5 flex items-center gap-1.5 text-xs text-muted-foreground">
                  <MapPin className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">{dossier.constateur.zone}</span>
                </div>
              </div>
            </div>
            <a
              href={`tel:${dossier.constateur.telephone.replace(/\s/g, "")}`}
              className="flex min-w-0 items-center gap-3 rounded-lg border border-border bg-muted/25 px-3 py-2.5 text-sm font-medium text-primary transition-colors hover:border-primary/30 hover:bg-primary/5"
            >
              <Phone className="h-4 w-4 shrink-0" />
              <span className="truncate">{dossier.constateur.telephone}</span>
            </a>
          </ContextPanel>
        </>
      }
    />
  );
}
