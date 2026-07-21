// Hooks React Query autour de src/lib/api.ts.
// Rafraîchissement automatique toutes les 15 s + refetch au focus fenêtre.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createWhatsappContact,
  deleteWhatsappContact,
  getCall,
  getDossier,
  getDossierCalls,
  getKpi,
  getSettings,
  listDossiers,
  listWhatsappContacts,
  putSettings,
  updateDossierM2s,
} from "@/lib/api";
import type { Dossier, Settings, WhatsappContact } from "@/data/types";
import type { DossierM2sUpdate } from "@/lib/api";

const LIST_OPTS = {
  refetchInterval: 15_000,
  refetchOnWindowFocus: true,
  staleTime: 5_000,
} as const;

const DETAIL_OPTS = {
  refetchInterval: 15_000,
  refetchOnWindowFocus: true,
  staleTime: 5_000,
} as const;

export function useDossiers(status?: "en_retard" | "valide") {
  return useQuery({
    queryKey: ["dossiers", status ?? "all"],
    queryFn: () => listDossiers(status),
    ...LIST_OPTS,
  });
}
export function useDossier(id: string) {
  return useQuery({
    queryKey: ["dossier", id],
    queryFn: () => getDossier(id),
    enabled: !!id,
    ...DETAIL_OPTS,
  });
}
export function useDossierCalls(id: string) {
  return useQuery({
    queryKey: ["dossier-calls", id],
    queryFn: () => getDossierCalls(id),
    enabled: !!id,
    ...DETAIL_OPTS,
  });
}
export function useCallDetail(id: string) {
  return useQuery({
    queryKey: ["call", id],
    queryFn: () => getCall(id),
    enabled: !!id,
    ...DETAIL_OPTS,
  });
}
export function useKpi() {
  return useQuery({
    queryKey: ["kpi"],
    queryFn: getKpi,
    ...LIST_OPTS,
  });
}
export function useSettings() {
  return useQuery({
    queryKey: ["settings"],
    queryFn: getSettings,
    staleTime: 60_000,
  });
}
export function useUpdateSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (s: Settings) => putSettings(s),
    onSuccess: (out) => qc.setQueryData(["settings"], out),
  });
}
export function useUpdateDossierM2s() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, values }: { id: string; values: DossierM2sUpdate }) =>
      updateDossierM2s(id, values),
    onSuccess: (out: Dossier) => {
      qc.setQueryData(["dossier", out.id], out);
      qc.invalidateQueries({ queryKey: ["dossiers"] });
      qc.invalidateQueries({ queryKey: ["valides"] });
    },
  });
}

export function useWhatsappContacts() {
  return useQuery({
    queryKey: ["whatsapp-contacts"],
    queryFn: listWhatsappContacts,
    staleTime: 60_000,
  });
}
export function useCreateWhatsappContact() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (c: Omit<WhatsappContact, "id">) => createWhatsappContact(c),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["whatsapp-contacts"] }),
  });
}
export function useDeleteWhatsappContact() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteWhatsappContact(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["whatsapp-contacts"] });
      qc.invalidateQueries({ queryKey: ["settings"] });
    },
  });
}
