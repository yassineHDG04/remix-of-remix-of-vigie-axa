# TP 5 et 6 — branchement du projet sur le schéma normalisé

Les TP 5 et 6 sont déjà implémentés dans cette version du projet.

## 1. Étape Supabase obligatoire

Dans **Supabase → SQL Editor**, ouvrir puis exécuter intégralement :

`supabase/migrations/20260716130000_rpc_dossiers_normalises.sql`

Ce script :

- vérifie que les objets des TP 1 à 4 existent ;
- crée la RPC transactionnelle `create_dossier_normalise` ;
- crée la RPC transactionnelle `update_dossier_m2s` ;
- limite leur exécution aux rôles `authenticated` et `service_role` ;
- recharge le cache de schéma PostgREST.

Le script conserve volontairement une **double écriture temporaire** dans les
anciennes colonnes de `dossiers`. Elle sécurise le TP 7. Après leur suppression
au TP 8, les RPC utilisent automatiquement uniquement les tables normalisées.

## 2. Vérification rapide dans SQL Editor

```sql
select
  to_regprocedure('public.create_dossier_normalise(text,uuid,uuid,timestamptz,double precision,timestamptz,text,integer,timestamptz,text,text,text,text,text,text,text,text,timestamptz)')
    as creation_rpc,
  to_regprocedure('public.update_dossier_m2s(uuid,text,text,text,text,text,text,text,timestamptz)')
    as modification_rpc;

select count(*) as dossiers_visibles
from public.v_dossiers_complets;
```

Les deux premières colonnes doivent contenir le nom complet d'une fonction et
la seconde requête doit s'exécuter sans erreur.

## 3. Ce qui a changé dans le code

- Le frontend lit les dossiers via `v_dossiers_complets`.
- La modification des informations M2S passe par `update_dossier_m2s`.
- L'import CSV crée client, véhicule, assurance, sinistre et dossier via
  `create_dossier_normalise`.
- Le backend Supabase lit également la vue et crée les nouveaux dossiers avec
  la même RPC transactionnelle.
- Les mises à jour purement opérationnelles (statut, relances, deadline,
  validation) restent faites sur `dossiers`.

## 4. Lancement pour le TP 7

Frontend :

```powershell
npm install
npm run dev
```

Backend, dans un second terminal :

```powershell
cd vigie-backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Ne lancez le TP 8 qu'après avoir validé : la liste critique, le détail, la
modification des informations M2S, la validation et la liste des dossiers
validés. Après le TP 8, régénérez idéalement `src/integrations/supabase/types.ts`
pour retirer les anciennes colonnes de ses types statiques.
