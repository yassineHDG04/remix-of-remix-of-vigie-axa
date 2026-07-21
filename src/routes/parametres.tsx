import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import {
  Bot,
  Database,
  MessageCircle,
  PhoneCall,
  Plus,
  RotateCcw,
  Save,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";
import {
  ConfigurationStatus,
  ContextItem,
  ContextPageLayout,
  ContextPanel,
} from "@/components/layout/ContextPageLayout";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ErrorState";
import type { Settings } from "@/data/types";
import {
  useCreateWhatsappContact,
  useDeleteWhatsappContact,
  useSettings,
  useUpdateSettings,
  useWhatsappContacts,
} from "@/lib/hooks";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/parametres")({
  component: Parametres,
  head: () => ({ meta: [{ title: "Paramètres · Nida'a M2S" }] }),
});

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label className="text-sm font-medium">{label}</Label>
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

type ThresholdKey = "relance1" | "relance2" | "relance3" | "relance4";
const THRESHOLD_KEYS: ThresholdKey[] = ["relance1", "relance2", "relance3", "relance4"];

function minutesToHHMM(total: number): string {
  const m = Math.max(0, Math.round(Number.isFinite(total) ? total : 0));
  const h = Math.floor(m / 60);
  const mm = m % 60;
  return `${String(h).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
}
function hhmmToMinutes(v: string): number {
  const [h, m] = v.split(":").map((x) => Number(x));
  if (!Number.isFinite(h) || !Number.isFinite(m)) return 0;
  return h * 60 + m;
}

function Parametres() {
  const settingsQ = useSettings();
  const update = useUpdateSettings();
  const contactsQ = useWhatsappContacts();
  const createContact = useCreateWhatsappContact();
  const deleteContact = useDeleteWhatsappContact();
  const [form, setForm] = useState<Settings | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [newContact, setNewContact] = useState({
    label: "",
    numberWhatsapp: "",
    whatsappToken: "",
    whatsappPhoneNumberId: "",
  });

  useEffect(() => {
    if (settingsQ.data) setForm(settingsQ.data);
  }, [settingsQ.data]);

  if (settingsQ.isError && !settingsQ.data) {
    return <ErrorState onRetry={() => settingsQ.refetch()} />;
  }
  if (!form) {
    return (
      <ContextPageLayout
        main={
          <>
            <Skeleton className="h-40 w-full" />
            <Skeleton className="h-40 w-full" />
          </>
        }
        aside={<Skeleton className="h-80 w-full" />}
      />
    );
  }

  function set<K extends keyof Settings>(k: K, v: Settings[K]) {
    setForm((f) => (f ? { ...f, [k]: v } : f));
  }
  function setThreshold(k: keyof Settings["thresholds"], v: number) {
    setForm((f) => (f ? { ...f, thresholds: { ...f.thresholds, [k]: v } } : f));
  }

  function setNbRelances(n: number) {
    setForm((f) => {
      if (!f) return f;
      const thresholds = { ...f.thresholds };
      // Préremplir les seuils nouvellement affichés s'ils sont incohérents.
      for (let i = 1; i <= n; i++) {
        const key = THRESHOLD_KEYS[i - 1];
        const prev = i === 1 ? undefined : thresholds[THRESHOLD_KEYS[i - 2]];
        const cur = thresholds[key];
        const invalid = !cur || cur <= thresholds.humain || (prev !== undefined && cur >= prev);
        if (invalid) {
          const upper = prev ?? cur ?? thresholds.humain + 180;
          thresholds[key] = Math.max(
            thresholds.humain + 15,
            Math.round((upper + thresholds.humain) / 2),
          );
        }
      }
      return { ...f, nbRelancesIa: n, thresholds };
    });
  }

  const N = Math.max(1, Math.min(4, form.nbRelancesIa));
  const selectedContact = (contactsQ.data ?? []).find(
    (contact) => contact.id === form.selectedWhatsappId,
  );
  const hasChanges = settingsQ.data
    ? JSON.stringify(form) !== JSON.stringify(settingsQ.data)
    : false;
  const voiceModel =
    form.voiceEngine === "realtime"
      ? form.realtimeModel
      : `${form.sttModel} · ${form.llmModel} · ${form.ttsModel}`;

  return (
    <form
      className="w-full"
      onSubmit={(e) => {
        e.preventDefault();
        if (!form) return;
        update.mutate(form, {
          onSuccess: () => toast.success("Paramètres enregistrés"),
          onError: (err) =>
            toast.error(
              err instanceof Error ? err.message : "Impossible d'enregistrer les paramètres",
            ),
        });
      }}
    >
      <ContextPageLayout
        main={
          <>
            <Card className="p-6 space-y-5">
              <div>
                <h2 className="text-base font-semibold">Seuils d'escalade</h2>
                <p className="text-sm text-muted-foreground">
                  Exprimés en minutes de temps restant avant la deadline SLA.
                </p>
              </div>

              <div className="space-y-1.5">
                <Label className="text-sm font-medium">Nombre de relances IA</Label>
                <div
                  className="inline-flex rounded-md border border-border bg-background p-0.5"
                  role="group"
                >
                  {[1, 2, 3, 4].map((n) => (
                    <button
                      key={n}
                      type="button"
                      onClick={() => setNbRelances(n)}
                      className={cn(
                        "min-w-10 px-3 py-1.5 text-sm font-medium rounded-[5px] transition-colors",
                        N === n
                          ? "bg-sidebar text-white shadow-sm"
                          : "text-muted-foreground hover:text-foreground hover:bg-muted",
                      )}
                      aria-pressed={N === n}
                    >
                      {n}
                    </button>
                  ))}
                </div>
                <p className="text-xs text-muted-foreground">
                  L'IA effectue ce nombre de relances avant de passer la main à l'humain.
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                {THRESHOLD_KEYS.slice(0, N).map((key, idx) => (
                  <Field key={key} label={`Seuil relance IA n°${idx + 1} (temps restant hh:mm)`}>
                    <Input
                      type="time"
                      step={60}
                      value={minutesToHHMM(form.thresholds[key])}
                      onChange={(e) => setThreshold(key, hhmmToMinutes(e.target.value))}
                    />
                  </Field>
                ))}
                <Field label="Seuil intervention humaine (temps restant hh:mm)">
                  <Input
                    type="time"
                    step={60}
                    value={minutesToHHMM(form.thresholds.humain)}
                    onChange={(e) => setThreshold("humain", hhmmToMinutes(e.target.value))}
                  />
                </Field>
              </div>

              <p className="text-xs text-muted-foreground border-t pt-3">
                Les seuils doivent être strictement décroissants, et le dernier doit rester
                supérieur au seuil d'intervention humaine.
              </p>
            </Card>

            <Card className="p-6 space-y-5">
              <div>
                <h2 className="text-base font-semibold">Boucle d'appel</h2>
                <p className="text-sm text-muted-foreground">Comportement en cas de non-réponse.</p>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                <Field
                  label="Stratégie d'appel"
                  hint="Le mode mixte tente WhatsApp avant de reprendre automatiquement le téléphone."
                >
                  <Select
                    value={form.callChannel}
                    onValueChange={(value: Settings["callChannel"]) => set("callChannel", value)}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="sip">Appel téléphonique uniquement</SelectItem>
                      <SelectItem value="whatsapp_then_sip">WhatsApp puis téléphone</SelectItem>
                    </SelectContent>
                  </Select>
                </Field>
                <Field
                  label="Tentatives WhatsApp avant téléphone"
                  hint="Après ce nombre de non-réponses, la boucle bascule vers le SIP."
                >
                  <Input
                    type="number"
                    min={1}
                    max={10}
                    disabled={form.callChannel !== "whatsapp_then_sip"}
                    value={form.whatsappMaxAttempts}
                    onChange={(e) => set("whatsappMaxAttempts", Number(e.target.value))}
                  />
                </Field>
                <Field
                  label="Intervalle de rappel (min)"
                  hint="Attente entre deux tentatives si non-réponse."
                >
                  <Input
                    type="number"
                    value={form.retryIntervalMin}
                    onChange={(e) => set("retryIntervalMin", Number(e.target.value))}
                  />
                </Field>
                <Field
                  label="Tentatives téléphoniques avant humain"
                  hint="Après l'épuisement du téléphone, le dossier passe au superviseur."
                >
                  <Input
                    type="number"
                    value={form.maxAttempts}
                    onChange={(e) => set("maxAttempts", Number(e.target.value))}
                  />
                </Field>
                <Field label="Fenêtre horaire — début">
                  <Input
                    type="time"
                    value={form.callWindow.start}
                    onChange={(e) =>
                      set("callWindow", { ...form.callWindow, start: e.target.value })
                    }
                  />
                </Field>
                <Field
                  label="Fenêtre horaire — fin"
                  hint="Aucun appel émis en dehors de la fenêtre."
                >
                  <Input
                    type="time"
                    value={form.callWindow.end}
                    onChange={(e) => set("callWindow", { ...form.callWindow, end: e.target.value })}
                  />
                </Field>
              </div>
              <div className="rounded-md border border-border bg-muted/40 p-3 text-xs leading-relaxed text-muted-foreground">
                {form.callChannel === "whatsapp_then_sip" ? (
                  <>
                    Ordre appliqué : <strong className="text-foreground">WhatsApp</strong> → sans
                    réponse,
                    <strong className="ml-1 text-foreground">appel téléphonique</strong> → sans
                    réponse,
                    <strong className="ml-1 text-foreground">intervention humaine</strong> et alerte
                    WhatsApp au superviseur sélectionné. Les permissions d'appel Meta et les secrets
                    du connecteur restent exclusivement dans le backend.
                  </>
                ) : (
                  <>
                    Ordre appliqué : <strong className="text-foreground">appel téléphonique</strong>{" "}
                    → sans réponse,{" "}
                    <strong className="text-foreground">intervention humaine</strong> et alerte
                    WhatsApp au superviseur sélectionné.
                  </>
                )}
              </div>
            </Card>

            <Card className="p-6 space-y-5">
              <div>
                <h2 className="text-base font-semibold">SLA & escalade humaine</h2>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                <Field
                  label="Durée SLA (heures)"
                  hint="Délai maximal entre arrivée du dossier et sa validation."
                >
                  <Input
                    type="number"
                    value={form.slaHours}
                    onChange={(e) => set("slaHours", Number(e.target.value))}
                  />
                </Field>
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <Label className="text-sm font-medium">Contact WhatsApp superviseur</Label>
                    <Dialog open={addOpen} onOpenChange={setAddOpen}>
                      <DialogTrigger asChild>
                        <Button type="button" size="sm" variant="outline" className="h-7 px-2">
                          <Plus className="h-3.5 w-3.5 mr-1" /> Ajouter
                        </Button>
                      </DialogTrigger>
                      <DialogContent>
                        <DialogHeader>
                          <DialogTitle>Nouveau contact WhatsApp</DialogTitle>
                          <DialogDescription>
                            Créez un profil d'alerte avec le superviseur destinataire, la clé API
                            M2S et l'instance WhatsApp expéditrice.
                          </DialogDescription>
                        </DialogHeader>
                        <div className="space-y-3">
                          <div className="space-y-1.5">
                            <Label className="text-sm">Libellé</Label>
                            <Input
                              placeholder="Zineb (superviseur)"
                              value={newContact.label}
                              onChange={(e) =>
                                setNewContact((c) => ({ ...c, label: e.target.value }))
                              }
                            />
                          </div>
                          <div className="space-y-1.5">
                            <Label className="text-sm">Numéro WhatsApp</Label>
                            <Input
                              placeholder="+212600000000"
                              value={newContact.numberWhatsapp}
                              onChange={(e) =>
                                setNewContact((c) => ({ ...c, numberWhatsapp: e.target.value }))
                              }
                            />
                          </div>
                          <div className="space-y-1.5">
                            <Label className="text-sm">Clé API M2S</Label>
                            <Input
                              type="password"
                              placeholder="m2s_..."
                              value={newContact.whatsappToken}
                              onChange={(e) =>
                                setNewContact((c) => ({ ...c, whatsappToken: e.target.value }))
                              }
                            />
                          </div>
                          <div className="space-y-1.5">
                            <Label className="text-sm">ID de l'instance expéditrice</Label>
                            <Input
                              placeholder="01kxnk84xwvmfr5dkc5kxcwtwh"
                              value={newContact.whatsappPhoneNumberId}
                              onChange={(e) =>
                                setNewContact((c) => ({
                                  ...c,
                                  whatsappPhoneNumberId: e.target.value,
                                }))
                              }
                            />
                          </div>
                        </div>
                        <DialogFooter>
                          <Button type="button" variant="outline" onClick={() => setAddOpen(false)}>
                            Annuler
                          </Button>
                          <Button
                            type="button"
                            disabled={
                              createContact.isPending ||
                              !newContact.numberWhatsapp.trim() ||
                              !newContact.whatsappToken.trim() ||
                              !newContact.whatsappPhoneNumberId.trim()
                            }
                            onClick={() => {
                              createContact.mutate(
                                {
                                  ...newContact,
                                  label: newContact.label.trim() || newContact.numberWhatsapp,
                                },
                                {
                                  onSuccess: (c) => {
                                    toast.success("Contact WhatsApp ajouté");
                                    set("selectedWhatsappId", c.id);
                                    setNewContact({
                                      label: "",
                                      numberWhatsapp: "",
                                      whatsappToken: "",
                                      whatsappPhoneNumberId: "",
                                    });
                                    setAddOpen(false);
                                  },
                                  onError: (err) =>
                                    toast.error(
                                      err instanceof Error
                                        ? err.message
                                        : "Impossible d'ajouter le contact",
                                    ),
                                },
                              );
                            }}
                          >
                            Ajouter
                          </Button>
                        </DialogFooter>
                      </DialogContent>
                    </Dialog>
                  </div>
                  <div className="flex items-center gap-2">
                    <Select
                      value={form.selectedWhatsappId ?? ""}
                      onValueChange={(v) => set("selectedWhatsappId", v || null)}
                    >
                      <SelectTrigger className="flex-1">
                        <SelectValue
                          placeholder={
                            contactsQ.data?.length
                              ? "Sélectionner un contact"
                              : "Aucun contact — ajouter"
                          }
                        />
                      </SelectTrigger>
                      <SelectContent>
                        {(contactsQ.data ?? []).map((c) => (
                          <SelectItem key={c.id} value={c.id}>
                            {c.label} — {c.numberWhatsapp}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      disabled={!form.selectedWhatsappId || deleteContact.isPending}
                      onClick={() => {
                        const id = form.selectedWhatsappId;
                        if (!id) return;
                        if (!confirm("Supprimer ce contact WhatsApp ?")) return;
                        deleteContact.mutate(id, {
                          onSuccess: () => {
                            toast.success("Contact supprimé");
                            set("selectedWhatsappId", null);
                          },
                          onError: (err) =>
                            toast.error(
                              err instanceof Error ? err.message : "Suppression impossible",
                            ),
                        });
                      }}
                      aria-label="Supprimer le contact sélectionné"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Numéro notifié en cas d'intervention humaine.
                  </p>
                </div>
              </div>
            </Card>

            <Card className="p-6 space-y-5">
              <div>
                <h2 className="text-base font-semibold">Synchronisation des dossiers M2S</h2>
                <p className="text-sm text-muted-foreground">
                  M2S reste la source de vérité : Vigie observe les validations sans permettre de
                  les produire depuis le dashboard.
                </p>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                <Field
                  label="Mode de synchronisation"
                  hint="Webhook recommandé ; polling disponible si M2S ne peut pas pousser les événements."
                >
                  <Select
                    value={form.m2sSyncMode}
                    onValueChange={(value: Settings["m2sSyncMode"]) => set("m2sSyncMode", value)}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="disabled">Désactivé</SelectItem>
                      <SelectItem value="webhook">Webhook (recommandé)</SelectItem>
                      <SelectItem value="polling">Polling API</SelectItem>
                    </SelectContent>
                  </Select>
                </Field>
                <Field
                  label="Cadence du polling (secondes)"
                  hint="Minimum 30 secondes. Utilisé uniquement en mode polling."
                >
                  <Input
                    type="number"
                    min={30}
                    max={86400}
                    disabled={form.m2sSyncMode !== "polling"}
                    value={form.m2sPollIntervalSeconds}
                    onChange={(e) => set("m2sPollIntervalSeconds", Number(e.target.value))}
                  />
                </Field>
                <div className="sm:col-span-2">
                  <Field
                    label="URL API dossiers M2S"
                    hint="L'URL et la cadence sont appliquées à chaud par le backend en mode polling."
                  >
                    <Input
                      value={form.m2sDossiersApiUrl}
                      placeholder="https://api.m2s.ma/dossiers"
                      disabled={form.m2sSyncMode !== "polling"}
                      onChange={(e) => set("m2sDossiersApiUrl", e.target.value)}
                    />
                  </Field>
                </div>
              </div>
              <div className="rounded-md border border-border bg-muted/40 p-3 text-xs leading-relaxed text-muted-foreground">
                <p>
                  Webhook :{" "}
                  <code className="font-mono text-foreground">
                    /api/webhooks/m2s/dossier-status
                  </code>
                </p>
                <p className="mt-1">
                  Les secrets <code className="font-mono text-foreground">M2S_WEBHOOK_SECRET</code>{" "}
                  et
                  <code className="ml-1 font-mono text-foreground">M2S_API_TOKEN</code> restent dans
                  le backend et ne sont jamais exposés dans cette page.
                </p>
              </div>
            </Card>

            <Card className="p-6 space-y-5">
              <div>
                <h2 className="text-base font-semibold">Téléphonie IA (SIP)</h2>
                <p className="text-sm text-muted-foreground">
                  Numéro utilisé par l'IA pour émettre les appels sortants.
                </p>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                <Field label="SIP_TRUNK_ID" hint="Identifiant du trunk SIP fourni par l'opérateur.">
                  <Input
                    value={form.sipTrunkId}
                    placeholder="trunk_xxx"
                    onChange={(e) => set("sipTrunkId", e.target.value)}
                  />
                </Field>
                <Field label="SIP_CALLER_ID" hint="Numéro affiché à l'appelé (Caller ID).">
                  <Input
                    value={form.sipCallerId}
                    placeholder="+212520000000"
                    onChange={(e) => set("sipCallerId", e.target.value)}
                  />
                </Field>
              </div>
            </Card>

            <Card className="p-6 space-y-5">
              <div>
                <h2 className="text-base font-semibold">Moteur vocal</h2>
                <p className="text-sm text-muted-foreground">
                  Bascule entre la qualité du speech-to-speech Realtime et un pipeline plus
                  économique. Le choix s'applique au prochain appel, sans redéploiement.
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                <Field label="Mode du moteur vocal">
                  <Select
                    value={form.voiceEngine}
                    onValueChange={(value: Settings["voiceEngine"]) => set("voiceEngine", value)}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="realtime">Realtime — qualité maximale</SelectItem>
                      <SelectItem value="pipeline">Pipeline — coût réduit</SelectItem>
                    </SelectContent>
                  </Select>
                </Field>

                {form.voiceEngine === "realtime" && (
                  <Field label="Modèle Realtime">
                    <Select
                      value={form.realtimeModel}
                      onValueChange={(value) => set("realtimeModel", value)}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="gpt-realtime">gpt-realtime</SelectItem>
                        <SelectItem value="gpt-realtime-mini">gpt-realtime-mini</SelectItem>
                      </SelectContent>
                    </Select>
                  </Field>
                )}
              </div>

              {form.voiceEngine === "pipeline" && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 border-t pt-4">
                  <Field label="Fournisseur STT" hint="Reconnaissance de la parole du constateur.">
                    <Select
                      value={form.sttProvider}
                      onValueChange={(value: Settings["sttProvider"]) => set("sttProvider", value)}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="openai">OpenAI</SelectItem>
                      </SelectContent>
                    </Select>
                  </Field>
                  <Field label="Modèle STT">
                    <Select value={form.sttModel} onValueChange={(value) => set("sttModel", value)}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="gpt-4o-mini-transcribe">
                          gpt-4o-mini-transcribe — économique
                        </SelectItem>
                        <SelectItem value="gpt-4o-transcribe">
                          gpt-4o-transcribe — qualité
                        </SelectItem>
                      </SelectContent>
                    </Select>
                  </Field>
                  <Field
                    label="Langue STT"
                    hint="Utilise ar pour la darija code-switchée ; ary n'est pas accepté par tous les modèles."
                  >
                    <Input
                      value={form.sttLanguage}
                      placeholder="ar"
                      onChange={(e) => set("sttLanguage", e.target.value)}
                    />
                  </Field>
                  <Field
                    label="Modèle LLM"
                    hint="Compréhension, function calling et réponse courte."
                  >
                    <Select value={form.llmModel} onValueChange={(value) => set("llmModel", value)}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="gpt-4o-mini">gpt-4o-mini — économique</SelectItem>
                        <SelectItem value="gpt-4.1-mini">gpt-4.1-mini — qualité</SelectItem>
                      </SelectContent>
                    </Select>
                  </Field>
                  <Field label="Fournisseur TTS" hint="Génération de la voix de l'assistant.">
                    <Select
                      value={form.ttsProvider}
                      onValueChange={(value: Settings["ttsProvider"]) => set("ttsProvider", value)}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="openai">OpenAI</SelectItem>
                      </SelectContent>
                    </Select>
                  </Field>
                  <Field label="Modèle TTS">
                    <Select value={form.ttsModel} onValueChange={(value) => set("ttsModel", value)}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="gpt-4o-mini-tts">gpt-4o-mini-tts</SelectItem>
                      </SelectContent>
                    </Select>
                  </Field>
                  <Field label="Voix TTS">
                    <Select
                      value={form.ttsVoiceId}
                      onValueChange={(value) => set("ttsVoiceId", value)}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="ash">ash</SelectItem>
                        <SelectItem value="coral">coral</SelectItem>
                        <SelectItem value="sage">sage</SelectItem>
                        <SelectItem value="verse">verse</SelectItem>
                      </SelectContent>
                    </Select>
                  </Field>
                </div>
              )}

              <div className="rounded-md border border-border bg-muted/40 p-3 text-xs leading-relaxed text-muted-foreground">
                Si le pipeline ne peut pas s'initialiser, le worker rebascule automatiquement sur
                Realtime et enregistre la raison dans la trace de l'appel.
              </div>
            </Card>

            <Card className="p-6 space-y-5">
              <div>
                <h2 className="text-base font-semibold">Agent vocal & LiveKit</h2>
                <p className="text-sm text-muted-foreground">
                  Connexion LiveKit, clé OpenAI et garde-fous de coût de l'agent vocal.
                </p>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                <Field label="LIVEKIT_URL" hint="URL wss:// de ton projet LiveKit Cloud.">
                  <Input
                    value={form.livekitUrl}
                    placeholder="wss://ton-projet.livekit.cloud"
                    onChange={(e) => set("livekitUrl", e.target.value)}
                  />
                </Field>
                <Field label="LIVEKIT_API_KEY">
                  <Input
                    value={form.livekitApiKey}
                    placeholder="API..."
                    onChange={(e) => set("livekitApiKey", e.target.value)}
                  />
                </Field>
                <Field label="LIVEKIT_API_SECRET">
                  <Input
                    type="password"
                    value={form.livekitApiSecret}
                    placeholder="••••••••"
                    onChange={(e) => set("livekitApiSecret", e.target.value)}
                  />
                </Field>
                <Field label="OPENAI_API_KEY" hint="Clé de l'agent vocal (OpenAI Realtime).">
                  <Input
                    type="password"
                    value={form.openaiApiKey}
                    placeholder="sk-..."
                    onChange={(e) => set("openaiApiKey", e.target.value)}
                  />
                </Field>
                <Field
                  label="VIGIE_API_BASE_URL"
                  hint="URL publique du backend (où l'agent poste les résultats d'appel)."
                >
                  <Input
                    value={form.vigieApiBaseUrl}
                    placeholder="https://ton-backend.onrender.com"
                    onChange={(e) => set("vigieApiBaseUrl", e.target.value)}
                  />
                </Field>
              </div>
              <div className="border-t pt-4">
                <p className="text-sm font-medium mb-3">Garde-fous de coût</p>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
                  <Field
                    label="Durée max d'appel (secondes)"
                    hint="Coupure dure, quoi qu'il arrive."
                  >
                    <Input
                      type="number"
                      value={form.agentMaxCallSeconds}
                      onChange={(e) => set("agentMaxCallSeconds", Number(e.target.value))}
                    />
                  </Field>
                  <Field label="Tokens max par réponse IA" hint="Longueur max d'un tour de parole.">
                    <Input
                      type="number"
                      value={form.agentMaxResponseTokens}
                      onChange={(e) => set("agentMaxResponseTokens", Number(e.target.value))}
                    />
                  </Field>
                  <Field label="Tours de parole max" hint="Clôture forcée au-delà.">
                    <Input
                      type="number"
                      value={form.agentMaxTurns}
                      onChange={(e) => set("agentMaxTurns", Number(e.target.value))}
                    />
                  </Field>
                </div>
              </div>
            </Card>
          </>
        }
        aside={
          <>
            <ContextPanel
              title="Résumé de la configuration"
              description="Aperçu des réglages qui seront appliqués aux prochains appels."
            >
              <ContextItem
                icon={PhoneCall}
                label="Stratégie d'appel"
                value={
                  form.callChannel === "whatsapp_then_sip"
                    ? "WhatsApp puis téléphone"
                    : "Téléphone uniquement"
                }
              />
              <ContextItem
                icon={Bot}
                label="Moteur vocal"
                value={
                  <div>
                    <div>{form.voiceEngine === "realtime" ? "Realtime" : "Pipeline"}</div>
                    <div className="mt-0.5 text-xs font-normal text-muted-foreground">
                      {voiceModel}
                    </div>
                  </div>
                }
              />
              <ContextItem
                icon={Database}
                label="Synchronisation M2S"
                value={
                  form.m2sSyncMode === "webhook"
                    ? "Webhook"
                    : form.m2sSyncMode === "polling"
                      ? `Polling toutes les ${form.m2sPollIntervalSeconds} s`
                      : "Désactivée"
                }
              />
              <ContextItem
                icon={MessageCircle}
                label="Superviseur alerté"
                value={
                  selectedContact ? (
                    <div>
                      <div>{selectedContact.label}</div>
                      <div className="mt-0.5 text-xs font-normal text-muted-foreground">
                        {selectedContact.numberWhatsapp}
                      </div>
                    </div>
                  ) : (
                    <span className="text-warning">Aucun contact sélectionné</span>
                  )
                }
              />
            </ContextPanel>

            <ContextPanel title="État des connexions">
              <ConfigurationStatus
                label="Téléphonie SIP"
                configured={Boolean(form.sipTrunkId.trim() && form.sipCallerId.trim())}
              />
              <ConfigurationStatus
                label="LiveKit"
                configured={Boolean(
                  form.livekitUrl.trim() &&
                  form.livekitApiKey.trim() &&
                  form.livekitApiSecret.trim(),
                )}
              />
              <ConfigurationStatus label="OpenAI" configured={Boolean(form.openaiApiKey.trim())} />
              <ConfigurationStatus
                label="Backend Vigie"
                configured={Boolean(form.vigieApiBaseUrl.trim())}
              />
            </ContextPanel>

            <Card className="p-4">
              <div
                className={cn(
                  "mb-3 rounded-lg border px-3 py-2 text-xs font-medium",
                  hasChanges
                    ? "border-warning/30 bg-warning/10 text-warning"
                    : "border-success/20 bg-success/10 text-success",
                )}
                aria-live="polite"
              >
                {hasChanges ? "Modifications non enregistrées" : "Configuration à jour"}
              </div>
              <div className="grid grid-cols-2 gap-2 xl:grid-cols-1 2xl:grid-cols-2">
                <Button
                  type="button"
                  variant="outline"
                  disabled={!hasChanges || update.isPending}
                  onClick={() => settingsQ.data && setForm(settingsQ.data)}
                >
                  <RotateCcw className="h-4 w-4" /> Annuler
                </Button>
                <Button type="submit" disabled={update.isPending || !hasChanges}>
                  <Save className="h-4 w-4" />
                  {update.isPending ? "Enregistrement…" : "Enregistrer"}
                </Button>
              </div>
            </Card>
          </>
        }
      />
    </form>
  );
}
