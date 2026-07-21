import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Search, Upload } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ErrorState";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { Zone } from "@/data/types";
import { formatDateTime } from "@/lib/time";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { pageNumbers } from "@/routes/superviseurs";

export const Route = createFileRoute("/valides")({
  component: Valides,
  head: () => ({ meta: [{ title: "Dossiers validés · Nida'a M2S" }] }),
});

const PAGE_SIZE = 25;
const MONTHS_FR = [
  "janvier",
  "février",
  "mars",
  "avril",
  "mai",
  "juin",
  "juillet",
  "août",
  "septembre",
  "octobre",
  "novembre",
  "décembre",
];

function isoWeek(d: Date): number {
  const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const day = t.getUTCDay() || 7;
  t.setUTCDate(t.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(t.getUTCFullYear(), 0, 1));
  return Math.ceil(((t.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
}
function weekRange(year: number, week: number): [Date, Date] {
  const simple = new Date(Date.UTC(year, 0, 4));
  const dayOfWeek = simple.getUTCDay() || 7;
  const iso1 = new Date(simple);
  iso1.setUTCDate(simple.getUTCDate() - dayOfWeek + 1);
  const start = new Date(iso1);
  start.setUTCDate(iso1.getUTCDate() + (week - 1) * 7);
  const end = new Date(start);
  end.setUTCDate(start.getUTCDate() + 7);
  return [start, end];
}

interface Row {
  id: string;
  ref_m2s: string;
  assure: string | null;
  nom_assurance: string | null;
  matricule: string | null;
  adresse: string | null;
  validated_at: string | null;
  constateurs: { nom: string; zone: string; telephone: string } | null;
}

function Valides() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [zone, setZone] = useState<"all" | Zone>("all");
  const [year, setYear] = useState<"all" | number>("all");
  const [month, setMonth] = useState<"all" | number>("all");
  const [week, setWeek] = useState<"all" | number>("all");
  const [page, setPage] = useState(1);
  const [importOpen, setImportOpen] = useState(false);

  // Reset page si filtres changent
  const filterKey = `${q}|${zone}|${year}|${month}|${week}`;
  useEffect(() => {
    setPage(1);
  }, [filterKey]);

  // Bornes de dates
  const [dateFrom, dateTo] = useMemo(() => {
    if (week !== "all" && year !== "all") return weekRange(year as number, week as number);
    if (month !== "all" && year !== "all") {
      const s = new Date(year as number, month as number, 1);
      const e = new Date(year as number, (month as number) + 1, 1);
      return [s, e];
    }
    if (year !== "all") {
      return [new Date(year as number, 0, 1), new Date((year as number) + 1, 0, 1)];
    }
    return [null, null] as [Date | null, Date | null];
  }, [year, month, week]);

  const dataQ = useQuery({
    queryKey: ["valides", { zone, year, month, week, page }],
    queryFn: async () => {
      const from = (page - 1) * PAGE_SIZE;
      const to = from + PAGE_SIZE - 1;
      let query = supabase
        .from("v_dossiers_complets")
        .select(
          "id, ref_m2s, assure, nom_assurance, matricule, adresse, validated_at, constateurs",
          { count: "exact" },
        )
        .eq("status", "valide")
        .order("validated_at", { ascending: false, nullsFirst: false })
        .range(from, to);
      if (dateFrom) query = query.gte("validated_at", dateFrom.toISOString());
      if (dateTo) query = query.lt("validated_at", dateTo.toISOString());
      const { data, error, count } = await query;
      if (error) throw new Error(error.message);
      return { rows: (data ?? []) as unknown as Row[], count: count ?? 0 };
    },
    refetchOnWindowFocus: true,
  });

  // Années disponibles
  const yearsQ = useQuery({
    queryKey: ["valides-years"],
    queryFn: async () => {
      const { data, error } = await supabase
        .from("dossiers")
        .select("validated_at")
        .eq("status", "valide")
        .not("validated_at", "is", null)
        .order("validated_at", { ascending: false })
        .limit(2000);
      if (error) throw new Error(error.message);
      const set = new Set<number>();
      for (const r of data ?? [])
        if (r.validated_at) set.add(new Date(r.validated_at).getFullYear());
      return Array.from(set).sort((a, b) => b - a);
    },
    staleTime: 60_000,
  });

  if (dataQ.isError && !dataQ.data) return <ErrorState onRetry={() => dataQ.refetch()} />;

  const allRows = dataQ.data?.rows ?? [];
  const rows = allRows.filter((d) => {
    if (zone !== "all" && d.constateurs?.zone !== zone) return false;
    if (q) {
      const s = q.toLowerCase();
      const searchable = [
        d.ref_m2s,
        d.assure,
        d.nom_assurance,
        d.matricule,
        d.adresse,
        d.constateurs?.nom,
      ];
      if (!searchable.some((value) => (value ?? "").toLowerCase().includes(s))) return false;
    }
    return true;
  });
  const total = dataQ.data?.count ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  function resetFilters() {
    setYear("all");
    setMonth("all");
    setWeek("all");
    setZone("all");
    setQ("");
    setPage(1);
  }

  return (
    <>
      <Card className="p-5">
        <div className="flex flex-wrap items-center gap-2 mb-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Réf., assuré, assurance…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              className="pl-9 w-64"
            />
          </div>
          <Select value={zone} onValueChange={(v) => setZone(v as never)}>
            <SelectTrigger className="w-36">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Toutes zones</SelectItem>
              {(["Casablanca", "Rabat", "Marrakech", "Tanger", "Agadir", "Fès"] as Zone[]).map(
                (z) => (
                  <SelectItem key={z} value={z}>
                    {z}
                  </SelectItem>
                ),
              )}
            </SelectContent>
          </Select>
          <Select
            value={String(year)}
            onValueChange={(v) => {
              setYear(v === "all" ? "all" : Number(v));
              setWeek("all");
            }}
          >
            <SelectTrigger className="w-32">
              <SelectValue placeholder="Année" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Toute année</SelectItem>
              {(yearsQ.data ?? [new Date().getFullYear()]).map((y) => (
                <SelectItem key={y} value={String(y)}>
                  {y}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={String(month)}
            onValueChange={(v) => {
              setMonth(v === "all" ? "all" : Number(v));
              setWeek("all");
            }}
            disabled={year === "all"}
          >
            <SelectTrigger className="w-36">
              <SelectValue placeholder="Mois" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Tout mois</SelectItem>
              {MONTHS_FR.map((m, i) => (
                <SelectItem key={m} value={String(i)}>
                  {m}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={String(week)}
            onValueChange={(v) => setWeek(v === "all" ? "all" : Number(v))}
            disabled={year === "all"}
          >
            <SelectTrigger className="w-40">
              <SelectValue placeholder="Semaine" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Toute semaine</SelectItem>
              {Array.from({ length: 53 }, (_, i) => i + 1).map((w) => (
                <SelectItem key={w} value={String(w)}>
                  Semaine {w}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button variant="ghost" size="sm" onClick={resetFilters}>
            Réinitialiser
          </Button>

          <div className="ml-auto">
            <Button variant="outline" onClick={() => setImportOpen(true)}>
              <Upload className="h-4 w-4 mr-1" /> Importer un CSV
            </Button>
          </div>
        </div>

        <div className="overflow-x-auto -mx-5">
          <div className="min-w-[960px] px-5">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Réf. sinistre</TableHead>
                  <TableHead>Assuré</TableHead>
                  <TableHead>Assurance</TableHead>
                  <TableHead>Matricule</TableHead>
                  <TableHead>Lieu du sinistre</TableHead>
                  <TableHead>Validé le</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {dataQ.isLoading &&
                  Array.from({ length: 4 }).map((_, i) => (
                    <TableRow key={i}>
                      {Array.from({ length: 6 }).map((_, j) => (
                        <TableCell key={j}>
                          <Skeleton className="h-4 w-full" />
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                {!dataQ.isLoading && rows.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center py-10 text-muted-foreground">
                      Aucun dossier validé.
                    </TableCell>
                  </TableRow>
                )}
                {rows.map((d) => (
                  <TableRow
                    key={d.id}
                    className="cursor-pointer"
                    tabIndex={0}
                    onClick={() => navigate({ to: "/dossiers/$id", params: { id: d.id } })}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        navigate({ to: "/dossiers/$id", params: { id: d.id } });
                      }
                    }}
                  >
                    <TableCell className="font-mono text-xs">{d.ref_m2s}</TableCell>
                    <TableCell>{d.assure?.trim() || "—"}</TableCell>
                    <TableCell>{d.nom_assurance?.trim() || "—"}</TableCell>
                    <TableCell>{d.matricule?.trim() || "—"}</TableCell>
                    <TableCell className="max-w-xs truncate" title={d.adresse || undefined}>
                      {d.adresse?.trim() || "—"}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {d.validated_at ? formatDateTime(new Date(d.validated_at)) : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>

        {totalPages > 1 && (
          <div className="mt-4 flex items-center justify-center gap-1 text-sm">
            <Button
              size="sm"
              variant="outline"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
            >
              Précédent
            </Button>
            {pageNumbers(page, totalPages).map((n, i) =>
              n === "…" ? (
                <span key={`e${i}`} className="px-2 text-muted-foreground">
                  …
                </span>
              ) : (
                <Button
                  key={n}
                  size="sm"
                  variant={n === page ? "default" : "outline"}
                  onClick={() => setPage(n as number)}
                >
                  {n}
                </Button>
              ),
            )}
            <Button
              size="sm"
              variant="outline"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
            >
              Suivant
            </Button>
          </div>
        )}
      </Card>

      <ImportCsvDialog
        open={importOpen}
        onOpenChange={setImportOpen}
        onImported={() => qc.invalidateQueries({ queryKey: ["valides"] })}
      />
    </>
  );
}

// ---------- CSV Import ----------

interface CsvRow {
  ref_m2s: string;
  constateur_nom: string;
  constateur_telephone: string;
  zone: string;
  arrival_at: string;
  validated_at?: string;
  delay_category?: string;
}

function parseCsv(text: string): CsvRow[] {
  const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0);
  if (lines.length === 0) return [];
  const header = splitCsvLine(lines[0]).map((h) => h.trim().toLowerCase());
  const idx = (name: string) => header.indexOf(name);
  const iRef = idx("ref_m2s"),
    iNom = idx("constateur_nom"),
    iTel = idx("constateur_telephone");
  const iZone = idx("zone"),
    iArr = idx("arrival_at"),
    iVal = idx("validated_at"),
    iCat = idx("delay_category");
  if ([iRef, iNom, iTel, iZone, iArr].some((v) => v < 0)) {
    throw new Error(
      "Colonnes attendues : ref_m2s, constateur_nom, constateur_telephone, zone, arrival_at (+ validated_at, delay_category)",
    );
  }
  const rows: CsvRow[] = [];
  for (let i = 1; i < lines.length; i++) {
    const c = splitCsvLine(lines[i]);
    rows.push({
      ref_m2s: (c[iRef] ?? "").trim(),
      constateur_nom: (c[iNom] ?? "").trim(),
      constateur_telephone: (c[iTel] ?? "").trim(),
      zone: (c[iZone] ?? "").trim(),
      arrival_at: (c[iArr] ?? "").trim(),
      validated_at: iVal >= 0 ? (c[iVal] ?? "").trim() : undefined,
      delay_category: iCat >= 0 ? (c[iCat] ?? "").trim() : undefined,
    });
  }
  return rows.filter((r) => r.ref_m2s);
}

function splitCsvLine(line: string): string[] {
  const out: string[] = [];
  let cur = "",
    inQ = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQ) {
      if (ch === '"' && line[i + 1] === '"') {
        cur += '"';
        i++;
      } else if (ch === '"') inQ = false;
      else cur += ch;
    } else {
      if (ch === '"') inQ = true;
      else if (ch === ",") {
        out.push(cur);
        cur = "";
      } else cur += ch;
    }
  }
  out.push(cur);
  return out;
}

function ImportCsvDialog({
  open,
  onOpenChange,
  onImported,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  onImported: () => void;
}) {
  const [preview, setPreview] = useState<CsvRow[] | null>(null);
  const [importing, setImporting] = useState(false);
  const [slaHours, setSlaHours] = useState(48);
  const inputRef = useRef<HTMLInputElement>(null);

  function onFile(f: File) {
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const rows = parseCsv(String(reader.result ?? ""));
        setPreview(rows);
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "CSV invalide");
      }
    };
    reader.readAsText(f);
  }

  async function doImport() {
    if (!preview) return;
    setImporting(true);
    let ok = 0,
      skipped = 0;
    try {
      // Cache existant : refs déjà présentes
      const refs = preview.map((r) => r.ref_m2s);
      const { data: existing } = await supabase
        .from("v_dossiers_complets")
        .select("ref_m2s")
        .in("ref_m2s", refs);
      const existingRefs = new Set((existing ?? []).map((e) => e.ref_m2s));

      for (const r of preview) {
        if (existingRefs.has(r.ref_m2s)) {
          skipped++;
          continue;
        }
        // Trouve / crée constateur par téléphone
        const { data: found } = await supabase
          .from("constateurs")
          .select("id")
          .eq("telephone", r.constateur_telephone)
          .maybeSingle();
        let cid = found?.id;
        if (!cid) {
          const { data: created, error: cErr } = await supabase
            .from("constateurs")
            .insert({ nom: r.constateur_nom, telephone: r.constateur_telephone, zone: r.zone })
            .select("id")
            .maybeSingle();
          if (cErr || !created) {
            skipped++;
            continue;
          }
          cid = created.id;
        }
        if (!cid) {
          skipped++;
          continue;
        }
        const arrival = r.arrival_at ? new Date(r.arrival_at) : new Date();
        const validated = r.validated_at ? new Date(r.validated_at) : new Date();
        const deadline = new Date(arrival.getTime() + slaHours * 3600_000);
        const { error: dErr } = await supabase.rpc("create_dossier_normalise", {
          p_ref_m2s: r.ref_m2s,
          p_constateur_id: cid,
          p_dossier_id: undefined,
          p_arrival_at: arrival.toISOString(),
          p_sla_hours: slaHours,
          p_deadline_at: deadline.toISOString(),
          p_status: "valide",
          p_current_stage: 0,
          p_validated_at: validated.toISOString(),
          p_final_category: r.delay_category || undefined,
          p_assure: "",
          p_num_tel_client: "",
          p_matricule: "",
          p_vehicule: "",
          p_nom_assurance: "",
          p_adresse: "",
          p_zone: "",
          p_date_sinistre: undefined,
        });
        if (dErr) skipped++;
        else ok++;
      }
      toast.success(`${ok} importés, ${skipped} ignorés`);
      onImported();
      onOpenChange(false);
      setPreview(null);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Erreur d'import");
    } finally {
      setImporting(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o);
        if (!o) setPreview(null);
      }}
    >
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Importer des dossiers validés (CSV)</DialogTitle>
        </DialogHeader>
        {!preview ? (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Colonnes :{" "}
              <code className="text-xs">
                ref_m2s, constateur_nom, constateur_telephone, zone, arrival_at, validated_at,
                delay_category
              </code>
            </p>
            <input
              ref={inputRef}
              type="file"
              accept=".csv,text/csv"
              onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
            />
            <div className="flex items-center gap-2 text-sm">
              <span>SLA (heures) par défaut :</span>
              <Input
                type="number"
                min={1}
                max={168}
                value={slaHours}
                onChange={(e) => setSlaHours(Number(e.target.value) || 48)}
                className="w-24"
              />
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="text-sm text-muted-foreground">Aperçu : {preview.length} lignes</div>
            <div className="max-h-64 overflow-auto rounded border border-border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Réf</TableHead>
                    <TableHead>Nom</TableHead>
                    <TableHead>Tel</TableHead>
                    <TableHead>Zone</TableHead>
                    <TableHead>Arrivée</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {preview.slice(0, 10).map((r, i) => (
                    <TableRow key={i}>
                      <TableCell className="font-mono text-xs">{r.ref_m2s}</TableCell>
                      <TableCell>{r.constateur_nom}</TableCell>
                      <TableCell>{r.constateur_telephone}</TableCell>
                      <TableCell>{r.zone}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {r.arrival_at}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Annuler
          </Button>
          {preview && (
            <Button onClick={doImport} disabled={importing}>
              {importing ? "Import…" : `Importer ${preview.length} lignes`}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
