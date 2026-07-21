import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowLeft, Bot, CalendarClock, Clock, DollarSign, PhoneCall } from "lucide-react";
import {
  ContextItem,
  ContextPageLayout,
  ContextPanel,
} from "@/components/layout/ContextPageLayout";
import { CallStatusBadge } from "@/components/StatusBadge";
import { ErrorState } from "@/components/ErrorState";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { DELAY_CATEGORY_LABEL } from "@/data/types";
import { formatDateTime, formatDuration, formatTime } from "@/lib/time";
import { useCallDetail, useDossier } from "@/lib/hooks";

export const Route = createFileRoute("/appels/$id")({
  component: CallDetailPage,
  head: () => ({ meta: [{ title: "Appel · Nida'a M2S" }] }),
});

function formatUsd(value: number): string {
  return new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 4,
    maximumFractionDigits: 4,
  }).format(value);
}

function modelRoleLabel(role: string): string {
  const labels: Record<string, string> = {
    realtime: "Realtime",
    stt: "STT",
    llm: "LLM",
    tts: "TTS",
    vad: "VAD",
  };
  return labels[role.toLowerCase()] ?? role.toUpperCase();
}

function CallDetailPage() {
  const { id } = Route.useParams();
  const callQ = useCallDetail(id);
  const dossierQ = useDossier(callQ.data?.call.dossierId ?? "");

  if (callQ.isLoading && !callQ.data) {
    return (
      <ContextPageLayout
        header={<Skeleton className="h-6 w-64" />}
        main={
          <>
            <Skeleton className="h-36 w-full" />
            <Skeleton className="h-72 w-full" />
          </>
        }
        aside={<Skeleton className="h-96 w-full" />}
      />
    );
  }
  if (callQ.isError || !callQ.data) {
    return <ErrorState onRetry={() => callQ.refetch()} />;
  }
  const { call, transcript } = callQ.data;
  const dossier = dossierQ.data;
  const modelEntries = Object.entries(call.modelsUsed ?? {});
  const channelLabel =
    call.callChannelUsed === "whatsapp"
      ? "Appel WhatsApp"
      : call.callChannelUsed === "sip"
        ? "Appel téléphonique SIP"
        : call.callChannelUsed === "mock"
          ? "Simulation"
          : "Non renseigné";
  const engineLabel =
    call.voiceEngineUsed === "realtime"
      ? "OpenAI Realtime"
      : call.voiceEngineUsed === "pipeline"
        ? "Pipeline STT → LLM → TTS"
        : call.voiceEngineUsed === "mock"
          ? "Simulation"
          : "Non renseigné";

  return (
    <ContextPageLayout
      header={
        dossier ? (
          <Link
            to="/dossiers/$id"
            params={{ id: dossier.id }}
            className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" /> Retour au dossier {dossier.refM2s}
          </Link>
        ) : null
      }
      main={
        <>
          <Card className="p-6">
            <div className="flex flex-wrap items-start justify-between gap-5">
              <div className="min-w-0">
                <div className="text-xs uppercase tracking-wide text-muted-foreground">Appel</div>
                <div className="mt-1 text-xl font-semibold">
                  {dossier?.refM2s ?? `#${call.id.slice(0, 8)}`}
                </div>
                <div className="mt-2 text-sm text-muted-foreground">
                  {dossier?.constateur.nom ?? "Constateur"} · Étape IA {call.stage} · Tentative{" "}
                  {call.attemptNo}
                </div>
              </div>
              <CallStatusBadge status={call.status} className="px-3 py-1 text-sm" />
            </div>
          </Card>

          {call.delayReason && (
            <Card className="bg-blue-soft/40 p-5">
              <div className="flex items-start justify-between gap-4 flex-wrap">
                <div>
                  <div className="text-xs uppercase tracking-wide text-muted-foreground font-medium">
                    Cause du retard (verbatim)
                  </div>
                  <blockquote
                    dir="auto"
                    className="mt-2 text-lg italic text-foreground leading-relaxed"
                  >
                    « {call.delayReason} »
                  </blockquote>
                </div>
                {call.delayCategory && (
                  <span className="inline-flex items-center rounded-full bg-accent px-3 py-1 text-xs font-semibold text-accent-foreground">
                    {DELAY_CATEGORY_LABEL[call.delayCategory]}
                  </span>
                )}
              </div>
            </Card>
          )}

          <div>
            <h2 className="text-sm font-semibold text-foreground mb-3 uppercase tracking-wide">
              Transcription
            </h2>
            {transcript.length === 0 ? (
              <Card className="p-8 text-center text-muted-foreground text-sm">
                Aucune transcription disponible pour cet appel.
              </Card>
            ) : (
              <Card className="p-5 space-y-3">
                {transcript.map((t) => {
                  const isIA = t.speaker === "ia";
                  return (
                    <div key={t.id} className={`flex ${isIA ? "justify-start" : "justify-end"}`}>
                      <div
                        dir="auto"
                        className={`max-w-[75%] rounded-2xl px-4 py-2.5 ${
                          isIA
                            ? "bg-blue-soft text-foreground rounded-tl-sm"
                            : "bg-muted text-foreground rounded-tr-sm"
                        }`}
                      >
                        <div className="text-[10px] uppercase tracking-wider font-medium mb-0.5 opacity-70">
                          {isIA ? "Assistant IA" : "Constateur"} · {formatTime(t.ts)}
                        </div>
                        <div className="text-sm leading-relaxed">{t.text}</div>
                      </div>
                    </div>
                  );
                })}
              </Card>
            )}
          </div>
        </>
      }
      aside={
        <>
          <ContextPanel title="Résumé de l'appel">
            <ContextItem
              label="Statut"
              value={<CallStatusBadge status={call.status} className="px-2.5 py-1" />}
            />
            <ContextItem icon={PhoneCall} label="Canal utilisé" value={channelLabel} />
            <ContextItem
              label="Étape et tentative"
              value={`Relance IA ${call.stage} · Tentative ${call.attemptNo}`}
            />
            <ContextItem
              icon={CalendarClock}
              label="Début"
              value={formatDateTime(call.startedAt)}
            />
            <ContextItem
              label="Fin"
              value={call.endedAt ? formatDateTime(call.endedAt) : "Appel en cours"}
            />
            <ContextItem
              icon={Clock}
              label="Durée"
              value={<span className="tabular-nums">{formatDuration(call.durationSec)}</span>}
            />
          </ContextPanel>

          <ContextPanel title="Moteur et coûts" description="Traçabilité technique de cet appel.">
            <ContextItem icon={Bot} label="Moteur vocal" value={engineLabel} />
            <ContextItem
              label="Modèles utilisés"
              value={
                modelEntries.length > 0 ? (
                  <div className="space-y-1.5">
                    {modelEntries.map(([role, model]) => (
                      <div key={role} className="flex items-start justify-between gap-3 text-xs">
                        <span className="font-normal text-muted-foreground">
                          {modelRoleLabel(role)}
                        </span>
                        <span className="break-all text-right font-mono font-medium">{model}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  "Non renseignés"
                )
              }
            />
            <ContextItem
              icon={DollarSign}
              label="Coût IA estimé"
              value={formatUsd(call.estimatedCostUsd)}
            />
            <ContextItem
              icon={DollarSign}
              label="Coût transport estimé"
              value={formatUsd(call.estimatedTransportCostUsd)}
            />
            {call.fallbackReason && (
              <div className="rounded-lg border border-warning/25 bg-warning/10 p-3">
                <div className="text-[11px] font-semibold uppercase tracking-wide text-warning">
                  Repli de canal ou de moteur
                </div>
                <p className="mt-1 break-words text-xs leading-relaxed text-muted-foreground">
                  {call.fallbackReason}
                </p>
              </div>
            )}
          </ContextPanel>
        </>
      }
    />
  );
}
