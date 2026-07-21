// Client de données Vigie — Lovable Cloud (Supabase Data API).
// Le surface d'API (signatures des fonctions exportées) est identique à la
// version précédente pour ne rien casser côté hooks/pages.

import type {
  Call,
  CallOutcome,
  CallStatus,
  Constateur,
  DelayCategory,
  Dossier,
  Kpi,
  Settings,
  TranscriptTurn,
  WhatsappContact,
  Zone,
} from "@/data/types";
import { supabase } from "@/integrations/supabase/client";

// ---------- Utils ----------
function toDate(v: string | null | undefined): Date {
  return new Date(v ?? new Date().toISOString());
}
function nullableDate(v: string | null | undefined): Date | undefined {
  return v ? new Date(v) : undefined;
}
function remainingMinutes(deadline: Date): number {
  return Math.round((deadline.getTime() - Date.now()) / 60_000);
}

// ---------- Mappers ----------
interface DbConstateur {
  id: string;
  nom: string;
  telephone: string;
  zone: string;
}
interface DbDossier {
  id: string;
  sinistre_id: string;
  client_id: string | null;
  vehicule_id: string | null;
  assurance_id: string | null;
  ref_m2s: string;
  arrival_at: string;
  sla_hours: number;
  deadline_at: string;
  status: string;
  current_stage: number;
  validated_at: string | null;
  handoff_reason: string | null;
  final_category: string | null;
  matricule: string | null;
  num_tel_client: string | null;
  nom_assurance: string | null;
  adresse: string | null;
  zone: string | null;
  assure: string | null;
  vehicule: string | null;
  date_sinistre: string | null;
  constateurs: DbConstateur | null;
}
interface DbCall {
  id: string;
  dossier_id: string;
  stage: number;
  attempt_no: number;
  started_at: string;
  ended_at: string | null;
  duration_sec: number;
  status: string;
  outcome: string | null;
  delay_reason: string | null;
  delay_category: string | null;
  voice_engine_used: string | null;
  models_used: Record<string, string> | null;
  estimated_cost_usd: number | null;
  call_channel_used: string | null;
  fallback_reason: string | null;
  provider_connected_at: string | null;
  estimated_transport_cost_usd: number | null;
}
interface DbTurn {
  call_id: string;
  turn_no: number;
  speaker: string;
  text: string;
  ts: string;
}
interface DbSettings {
  id: number;
  nb_relances_ia: number;
  relance1_min: number;
  relance2_min: number;
  relance3_min: number;
  relance4_min: number;
  humain_min: number;
  retry_interval_min: number;
  max_attempts: number;
  call_channel: string | null;
  whatsapp_max_attempts: number | null;
  call_window_start: string;
  call_window_end: string;
  sla_hours: number;
  selected_whatsapp_id: string | null;
  sip_trunk_id: string | null;
  sip_caller_id: string | null;
  livekit_url: string | null;
  livekit_api_key: string | null;
  livekit_api_secret: string | null;
  openai_api_key: string | null;
  vigie_api_base_url: string | null;
  agent_max_call_seconds: number | null;
  agent_max_response_tokens: number | null;
  agent_max_turns: number | null;
  voice_engine: string | null;
  realtime_model: string | null;
  stt_provider: string | null;
  stt_model: string | null;
  stt_language: string | null;
  llm_model: string | null;
  tts_provider: string | null;
  tts_model: string | null;
  tts_voice_id: string | null;
  m2s_sync_mode: string | null;
  m2s_dossiers_api_url: string | null;
  m2s_poll_interval_seconds: number | null;
}
interface DbWhatsappContact {
  id: string;
  label: string;
  number_whatsapp: string;
  whatsapp_token: string;
  whatsapp_phone_number_id: string;
}

function mapConstateur(c: DbConstateur | null): Constateur {
  if (!c) return { id: "", nom: "—", telephone: "", zone: "Casablanca" };
  return { id: c.id, nom: c.nom, telephone: c.telephone, zone: (c.zone as Zone) || "Casablanca" };
}
function mapDossier(d: DbDossier): Dossier {
  const deadline = toDate(d.deadline_at);
  return {
    id: d.id,
    sinistreId: d.sinistre_id,
    clientId: d.client_id,
    vehiculeId: d.vehicule_id,
    assuranceId: d.assurance_id,
    refM2s: d.ref_m2s,
    constateur: mapConstateur(d.constateurs),
    arrivalAt: toDate(d.arrival_at),
    slaHours: d.sla_hours,
    deadlineAt: deadline,
    status: d.status === "valide" ? "valide" : "en_retard",
    currentStage: Math.max(0, d.current_stage ?? 0),
    validatedAt: nullableDate(d.validated_at),
    handoffReason: d.handoff_reason ?? undefined,
    remainingMinutes: d.status === "valide" ? null : remainingMinutes(deadline),
    finalCategory: (d.final_category as DelayCategory | null) ?? undefined,
    matricule: d.matricule ?? undefined,
    numTelClient: d.num_tel_client ?? undefined,
    nomAssurance: d.nom_assurance ?? undefined,
    adresse: d.adresse ?? undefined,
    zoneDossier: d.zone ?? undefined,
    assure: d.assure ?? "",
    vehicule: d.vehicule ?? "",
    dateSinistre: d.date_sinistre ? new Date(d.date_sinistre) : null,
  };
}
function mapCall(c: DbCall): Call {
  return {
    id: c.id,
    dossierId: c.dossier_id,
    stage: Math.max(1, Math.min(4, c.stage)) as Call["stage"],
    attemptNo: Math.max(1, c.attempt_no),
    startedAt: toDate(c.started_at),
    endedAt: c.ended_at ? new Date(c.ended_at) : null,
    durationSec: c.duration_sec,
    status: (c.status as CallStatus) ?? "echec",
    outcome: (c.outcome as CallOutcome | null) ?? null,
    delayReason: c.delay_reason ?? undefined,
    delayCategory: (c.delay_category as DelayCategory | null) ?? undefined,
    voiceEngineUsed:
      c.voice_engine_used === "realtime" ||
      c.voice_engine_used === "pipeline" ||
      c.voice_engine_used === "mock"
        ? c.voice_engine_used
        : undefined,
    modelsUsed: c.models_used ?? {},
    estimatedCostUsd: c.estimated_cost_usd ?? 0,
    callChannelUsed:
      c.call_channel_used === "sip" ||
      c.call_channel_used === "whatsapp" ||
      c.call_channel_used === "mock"
        ? c.call_channel_used
        : undefined,
    fallbackReason: c.fallback_reason ?? undefined,
    providerConnectedAt: nullableDate(c.provider_connected_at),
    estimatedTransportCostUsd: c.estimated_transport_cost_usd ?? 0,
  };
}
function mapTurn(t: DbTurn): TranscriptTurn {
  return {
    id: `${t.call_id}-t${t.turn_no}`,
    callId: t.call_id,
    turnNo: t.turn_no,
    speaker: t.speaker === "ia" ? "ia" : "constateur",
    text: t.text,
    ts: toDate(t.ts),
  };
}
function mapWhatsappContact(c: DbWhatsappContact): WhatsappContact {
  return {
    id: c.id,
    label: c.label ?? "",
    numberWhatsapp: c.number_whatsapp,
    whatsappToken: c.whatsapp_token ?? "",
    whatsappPhoneNumberId: c.whatsapp_phone_number_id ?? "",
  };
}
function mapSettings(s: DbSettings): Settings {
  return {
    nbRelancesIa: Math.max(1, Math.min(4, s.nb_relances_ia ?? 3)),
    thresholds: {
      relance1: s.relance1_min,
      relance2: s.relance2_min,
      relance3: s.relance3_min,
      relance4: s.relance4_min,
      humain: s.humain_min,
    },
    retryIntervalMin: s.retry_interval_min,
    maxAttempts: s.max_attempts,
    callChannel: s.call_channel === "whatsapp_then_sip" ? "whatsapp_then_sip" : "sip",
    whatsappMaxAttempts: s.whatsapp_max_attempts ?? 2,
    callWindow: { start: s.call_window_start, end: s.call_window_end },
    slaHours: s.sla_hours,
    selectedWhatsappId: s.selected_whatsapp_id ?? null,
    sipTrunkId: s.sip_trunk_id ?? "",
    sipCallerId: s.sip_caller_id ?? "",
    livekitUrl: s.livekit_url ?? "",
    livekitApiKey: s.livekit_api_key ?? "",
    livekitApiSecret: s.livekit_api_secret ?? "",
    openaiApiKey: s.openai_api_key ?? "",
    vigieApiBaseUrl: s.vigie_api_base_url ?? "",
    agentMaxCallSeconds: s.agent_max_call_seconds ?? 60,
    agentMaxResponseTokens: s.agent_max_response_tokens ?? 200,
    agentMaxTurns: s.agent_max_turns ?? 6,
    voiceEngine: s.voice_engine === "pipeline" ? "pipeline" : "realtime",
    realtimeModel: s.realtime_model ?? "gpt-realtime",
    sttProvider: "openai",
    sttModel: s.stt_model ?? "gpt-4o-mini-transcribe",
    sttLanguage: s.stt_language ?? "ar",
    llmModel: s.llm_model ?? "gpt-4o-mini",
    ttsProvider: "openai",
    ttsModel: s.tts_model ?? "gpt-4o-mini-tts",
    ttsVoiceId: s.tts_voice_id ?? "ash",
    m2sSyncMode:
      s.m2s_sync_mode === "webhook" || s.m2s_sync_mode === "polling" ? s.m2s_sync_mode : "disabled",
    m2sDossiersApiUrl: s.m2s_dossiers_api_url ?? "",
    m2sPollIntervalSeconds: s.m2s_poll_interval_seconds ?? 300,
  };
}
function settingsToDb(s: Settings) {
  return {
    nb_relances_ia: s.nbRelancesIa,
    relance1_min: s.thresholds.relance1,
    relance2_min: s.thresholds.relance2,
    relance3_min: s.thresholds.relance3,
    relance4_min: s.thresholds.relance4,
    humain_min: s.thresholds.humain,
    retry_interval_min: s.retryIntervalMin,
    max_attempts: s.maxAttempts,
    call_channel: s.callChannel,
    whatsapp_max_attempts: s.whatsappMaxAttempts,
    call_window_start: s.callWindow.start,
    call_window_end: s.callWindow.end,
    sla_hours: s.slaHours,
    selected_whatsapp_id: s.selectedWhatsappId,
    sip_trunk_id: s.sipTrunkId,
    sip_caller_id: s.sipCallerId,
    livekit_url: s.livekitUrl,
    livekit_api_key: s.livekitApiKey,
    livekit_api_secret: s.livekitApiSecret,
    openai_api_key: s.openaiApiKey,
    vigie_api_base_url: s.vigieApiBaseUrl,
    agent_max_call_seconds: s.agentMaxCallSeconds,
    agent_max_response_tokens: s.agentMaxResponseTokens,
    agent_max_turns: s.agentMaxTurns,
    voice_engine: s.voiceEngine,
    realtime_model: s.realtimeModel,
    stt_provider: s.sttProvider,
    stt_model: s.sttModel,
    stt_language: s.sttLanguage,
    llm_model: s.llmModel,
    tts_provider: s.ttsProvider,
    tts_model: s.ttsModel,
    tts_voice_id: s.ttsVoiceId,
    m2s_sync_mode: s.m2sSyncMode,
    m2s_dossiers_api_url: s.m2sDossiersApiUrl,
    m2s_poll_interval_seconds: s.m2sPollIntervalSeconds,
  };
}

const DOSSIER_SELECT =
  "id, sinistre_id, client_id, vehicule_id, assurance_id, ref_m2s, arrival_at, sla_hours, deadline_at, status, current_stage, validated_at, handoff_reason, final_category, matricule, num_tel_client, nom_assurance, adresse, zone, assure, vehicule, date_sinistre, constateurs";

export type DossierM2sUpdate = Pick<
  Dossier,
  | "assure"
  | "vehicule"
  | "matricule"
  | "adresse"
  | "zoneDossier"
  | "dateSinistre"
  | "nomAssurance"
  | "numTelClient"
>;

// ---------- Validations (règles métier, avant écriture) ----------
function validateSettings(s: Settings): void {
  const t = s.thresholds;
  const N = Math.max(1, Math.min(4, s.nbRelancesIa));
  const keys: (keyof typeof t)[] = ["relance1", "relance2", "relance3", "relance4"];
  for (let i = 0; i < N; i++) {
    if (!Number.isFinite(t[keys[i]]) || t[keys[i]] <= 0)
      throw new Error(`Le seuil relance IA n°${i + 1} doit être un entier positif.`);
  }
  if (!Number.isFinite(t.humain) || t.humain <= 0)
    throw new Error("Le seuil d'intervention humaine doit être un entier positif.");
  if (
    !Number.isFinite(s.whatsappMaxAttempts) ||
    s.whatsappMaxAttempts < 1 ||
    s.whatsappMaxAttempts > 10
  )
    throw new Error("Le nombre de tentatives WhatsApp doit être compris entre 1 et 10.");
  for (let i = 0; i < N - 1; i++) {
    if (t[keys[i]] <= t[keys[i + 1]])
      throw new Error("Les seuils de relance IA doivent être strictement décroissants.");
  }
  if (t[keys[N - 1]] <= t.humain)
    throw new Error("Le dernier seuil IA doit rester supérieur au seuil humain.");
  if (
    !Number.isFinite(s.m2sPollIntervalSeconds) ||
    s.m2sPollIntervalSeconds < 30 ||
    s.m2sPollIntervalSeconds > 86_400
  )
    throw new Error("La cadence M2S doit être comprise entre 30 et 86 400 secondes.");
  if (!s.realtimeModel.trim()) throw new Error("Le modèle Realtime est obligatoire.");
  if (s.voiceEngine === "pipeline") {
    const required = [s.sttModel, s.sttLanguage, s.llmModel, s.ttsModel, s.ttsVoiceId];
    if (required.some((value) => !value.trim()))
      throw new Error("Tous les paramètres du pipeline vocal sont obligatoires.");
  }
}

// ---------- Endpoints publics ----------
export async function listDossiers(status?: "en_retard" | "valide"): Promise<Dossier[]> {
  let q = supabase
    .from("v_dossiers_complets")
    .select(DOSSIER_SELECT)
    .order("deadline_at", { ascending: true });
  if (status) q = q.eq("status", status);
  const { data, error } = await q;
  if (error) throw new Error(error.message);
  return (data ?? []).map((d) => mapDossier(d as unknown as DbDossier));
}

export async function getDossier(id: string): Promise<Dossier> {
  const { data, error } = await supabase
    .from("v_dossiers_complets")
    .select(DOSSIER_SELECT)
    .eq("id", id)
    .maybeSingle();
  if (error) throw new Error(error.message);
  if (!data) throw new Error("Dossier introuvable.");
  return mapDossier(data as unknown as DbDossier);
}

export async function updateDossierM2s(id: string, values: DossierM2sUpdate): Promise<Dossier> {
  const { error } = await supabase.rpc("update_dossier_m2s", {
    p_dossier_id: id,
    p_assure: values.assure ?? "",
    p_num_tel_client: values.numTelClient ?? "",
    p_matricule: values.matricule ?? "",
    p_vehicule: values.vehicule ?? "",
    p_nom_assurance: values.nomAssurance ?? "",
    p_adresse: values.adresse ?? "",
    p_zone: values.zoneDossier ?? "",
    p_date_sinistre: values.dateSinistre ? values.dateSinistre.toISOString() : undefined,
  });
  if (error) throw new Error(error.message);
  return getDossier(id);
}

export async function getDossierCalls(dossierId: string): Promise<Call[]> {
  const { data, error } = await supabase
    .from("calls")
    .select("*")
    .eq("dossier_id", dossierId)
    .order("started_at", { ascending: true });
  if (error) throw new Error(error.message);
  return (data ?? []).map((c) => mapCall(c as DbCall));
}

export async function getCall(id: string): Promise<{ call: Call; transcript: TranscriptTurn[] }> {
  const [{ data: cRow, error: cErr }, { data: tRows, error: tErr }] = await Promise.all([
    supabase.from("calls").select("*").eq("id", id).maybeSingle(),
    supabase
      .from("transcript_turns")
      .select("call_id, turn_no, speaker, text, ts")
      .eq("call_id", id)
      .order("turn_no", { ascending: true }),
  ]);
  if (cErr) throw new Error(cErr.message);
  if (!cRow) throw new Error("Appel introuvable.");
  if (tErr) throw new Error(tErr.message);
  return {
    call: mapCall(cRow as DbCall),
    transcript: (tRows ?? []).map((t) => mapTurn(t as DbTurn)),
  };
}

export async function getKpi(): Promise<Kpi> {
  // KPI calculés client-side à partir de comptages ciblés.
  const nowIso = new Date().toISOString();
  const inOneHour = new Date(Date.now() + 60 * 60 * 1000).toISOString();
  const todayStart = new Date();
  todayStart.setHours(0, 0, 0, 0);

  const [enRetardQ, critiquesQ, handoffQ, validesQ, appelsTodayQ, prisTodayQ] = await Promise.all([
    supabase
      .from("dossiers")
      .select("id", { count: "exact", head: true })
      .eq("status", "en_retard"),
    supabase
      .from("dossiers")
      .select("id", { count: "exact", head: true })
      .eq("status", "en_retard")
      .lte("deadline_at", inOneHour)
      .gte("deadline_at", nowIso),
    supabase
      .from("dossiers")
      .select("id", { count: "exact", head: true })
      .eq("status", "en_retard")
      .not("handoff_reason", "is", null),
    supabase
      .from("dossiers")
      .select("id", { count: "exact", head: true })
      .eq("status", "valide")
      .gte("validated_at", todayStart.toISOString()),
    supabase
      .from("calls")
      .select("id", { count: "exact", head: true })
      .gte("started_at", todayStart.toISOString()),
    supabase
      .from("calls")
      .select("id", { count: "exact", head: true })
      .gte("started_at", todayStart.toISOString())
      .eq("status", "pris"),
  ]);

  const appelsTotal = appelsTodayQ.count ?? 0;
  const pris = prisTodayQ.count ?? 0;

  return {
    en_retard: enRetardQ.count ?? 0,
    critiques_1h: critiquesQ.count ?? 0,
    en_handoff_humain: handoffQ.count ?? 0,
    valides_aujourdhui: validesQ.count ?? 0,
    appels_aujourdhui: appelsTotal,
    taux_decroche_pct: appelsTotal > 0 ? Math.round((pris / appelsTotal) * 100) : 0,
  };
}

export async function getSettings(): Promise<Settings> {
  const { data, error } = await supabase.from("settings").select("*").eq("id", 1).maybeSingle();
  if (error) throw new Error(error.message);
  if (!data) throw new Error("Paramètres introuvables.");
  return mapSettings(data as DbSettings);
}

export async function putSettings(s: Settings): Promise<Settings> {
  validateSettings(s);
  const { data, error } = await supabase
    .from("settings")
    .update(settingsToDb(s))
    .eq("id", 1)
    .select("*")
    .maybeSingle();
  if (error) throw new Error(error.message);
  if (!data) throw new Error("Impossible d'enregistrer les paramètres.");
  return mapSettings(data as DbSettings);
}

// ---------- WhatsApp contacts ----------
export async function listWhatsappContacts(): Promise<WhatsappContact[]> {
  const { data, error } = await (
    supabase as unknown as {
      from: (t: string) => {
        select: (s: string) => {
          order: (
            c: string,
            o: { ascending: boolean },
          ) => Promise<{ data: DbWhatsappContact[] | null; error: { message: string } | null }>;
        };
      };
    }
  )
    .from("whatsapp_contacts")
    .select("id, label, number_whatsapp, whatsapp_token, whatsapp_phone_number_id")
    .order("created_at", { ascending: true });
  if (error) throw new Error(error.message);
  return (data ?? []).map(mapWhatsappContact);
}

export async function createWhatsappContact(
  input: Omit<WhatsappContact, "id">,
): Promise<WhatsappContact> {
  const payload = {
    label: input.label,
    number_whatsapp: input.numberWhatsapp,
    whatsapp_token: input.whatsappToken,
    whatsapp_phone_number_id: input.whatsappPhoneNumberId,
  };
  const { data, error } = await (
    supabase as unknown as {
      from: (t: string) => {
        insert: (v: unknown) => {
          select: (s: string) => {
            maybeSingle: () => Promise<{
              data: DbWhatsappContact | null;
              error: { message: string } | null;
            }>;
          };
        };
      };
    }
  )
    .from("whatsapp_contacts")
    .insert(payload)
    .select("id, label, number_whatsapp, whatsapp_token, whatsapp_phone_number_id")
    .maybeSingle();
  if (error) throw new Error(error.message);
  if (!data) throw new Error("Impossible d'ajouter le contact WhatsApp.");
  return mapWhatsappContact(data);
}

export async function deleteWhatsappContact(id: string): Promise<void> {
  const { error } = await (
    supabase as unknown as {
      from: (t: string) => {
        delete: () => {
          eq: (c: string, v: string) => Promise<{ error: { message: string } | null }>;
        };
      };
    }
  )
    .from("whatsapp_contacts")
    .delete()
    .eq("id", id);
  if (error) throw new Error(error.message);
}
