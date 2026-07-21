export type Zone = "Casablanca" | "Rabat" | "Marrakech" | "Tanger" | "Agadir" | "Fès";

export interface Constateur {
  id: string;
  nom: string;
  telephone: string;
  zone: Zone;
}

export type DossierStatus = "en_retard" | "valide";

export interface Dossier {
  id: string;
  sinistreId?: string;
  clientId?: string | null;
  vehiculeId?: string | null;
  assuranceId?: string | null;
  refM2s: string;
  constateur: Constateur;
  arrivalAt: Date;
  slaHours: number;
  deadlineAt: Date;
  status: DossierStatus;
  /** 0 = en attente, 1..N = relances IA, N+1 = humain (déduire via handoffReason). */
  currentStage: number;
  validatedAt?: Date;
  handoffReason?: string;
  remainingMinutes: number | null;
  finalCategory?: DelayCategory;
  matricule?: string;
  numTelClient?: string;
  nomAssurance?: string;
  adresse?: string;
  zoneDossier?: string;
  assure: string;
  vehicule: string;
  dateSinistre: Date | null;
}

export interface WhatsappContact {
  id: string;
  label: string;
  numberWhatsapp: string;
  whatsappToken: string;
  whatsappPhoneNumberId: string;
}

export type CallStatus = "en_cours" | "pris" | "non_joignable" | "repondeur" | "refus" | "echec";

export type CallOutcome = "cause_captee" | "non_joignable" | "hors_sujet" | "refus";

export type DelayCategory =
  | "desaccord_parties"
  | "zone_hors_km"
  | "expertise_en_cours"
  | "pieces_manquantes"
  | "injoignable_tiers"
  | "autre";

export interface Call {
  id: string;
  dossierId: string;
  stage: 1 | 2 | 3 | 4;
  attemptNo: number;
  startedAt: Date;
  endedAt: Date | null;
  durationSec: number;
  status: CallStatus;
  outcome: CallOutcome | null;
  delayReason?: string;
  delayCategory?: DelayCategory;
  voiceEngineUsed?: "realtime" | "pipeline" | "mock";
  modelsUsed: Record<string, string>;
  estimatedCostUsd: number;
  callChannelUsed?: "sip" | "whatsapp" | "mock";
  fallbackReason?: string;
  providerConnectedAt?: Date;
  estimatedTransportCostUsd: number;
}

export interface TranscriptTurn {
  id: string;
  callId: string;
  turnNo: number;
  speaker: "ia" | "constateur";
  text: string;
  ts: Date;
}

export interface Kpi {
  en_retard: number;
  critiques_1h: number;
  en_handoff_humain: number;
  valides_aujourdhui: number;
  appels_aujourdhui: number;
  taux_decroche_pct: number;
}

export interface Settings {
  /** Nombre de relances IA effectuées avant hand-off humain (1 à 4). */
  nbRelancesIa: number;
  thresholds: {
    relance1: number;
    relance2: number;
    relance3: number;
    relance4: number;
    humain: number;
  };
  retryIntervalMin: number;
  maxAttempts: number;
  /** Stratégie de canal : historique SIP ou WhatsApp avec repli SIP. */
  callChannel: "sip" | "whatsapp_then_sip";
  whatsappMaxAttempts: number;
  callWindow: { start: string; end: string };
  slaHours: number;
  /** Id du contact WhatsApp sélectionné pour recevoir les notifications. */
  selectedWhatsappId: string | null;
  /** SIP trunk utilisé pour émettre les appels IA. */
  sipTrunkId: string;
  /** Identifiant appelant SIP (numéro affiché). */
  sipCallerId: string;
  livekitUrl: string;
  livekitApiKey: string;
  livekitApiSecret: string;
  openaiApiKey: string;
  vigieApiBaseUrl: string;
  agentMaxCallSeconds: number;
  agentMaxResponseTokens: number;
  agentMaxTurns: number;
  /** Moteur construit au démarrage de chaque job LiveKit. */
  voiceEngine: "realtime" | "pipeline";
  realtimeModel: string;
  sttProvider: "openai";
  sttModel: string;
  sttLanguage: string;
  llmModel: string;
  ttsProvider: "openai";
  ttsModel: string;
  ttsVoiceId: string;
  /** Canal par lequel Vigie observe les changements de statut dans M2S. */
  m2sSyncMode: "disabled" | "webhook" | "polling";
  /** URL de lecture des dossiers, utilisée uniquement en mode polling. */
  m2sDossiersApiUrl: string;
  m2sPollIntervalSeconds: number;
}

export const DELAY_CATEGORY_LABEL: Record<DelayCategory, string> = {
  desaccord_parties: "Désaccord entre parties",
  zone_hors_km: "Zone hors kilométrage",
  expertise_en_cours: "Expertise en cours",
  pieces_manquantes: "Pièces manquantes",
  injoignable_tiers: "Tiers injoignable",
  autre: "Autre",
};

export const CALL_STATUS_LABEL: Record<CallStatus, string> = {
  en_cours: "En cours",
  pris: "Pris",
  non_joignable: "Non joignable",
  repondeur: "Répondeur",
  refus: "Refus",
  echec: "Échec",
};
