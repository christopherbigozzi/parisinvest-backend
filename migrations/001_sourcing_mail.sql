-- ============================================================================
-- 001_sourcing_mail.sql
-- Passage du sourcing API Melo au sourcing par alertes mail.
-- À exécuter dans Supabase → SQL Editor. Idempotent, réexécutable sans risque.
-- ============================================================================

-- ── Nouvelles colonnes sur annonces ─────────────────────────────────────────
alter table public.annonces add column if not exists empreinte     text;
alter table public.annonces add column if not exists principal     boolean default true;
alter table public.annonces add column if not exists description   text;
alter table public.annonces add column if not exists pieces        integer;
alter table public.annonces add column if not exists etage         text;
alter table public.annonces add column if not exists prix_m2_ref   numeric;
alter table public.annonces add column if not exists gmail_id      text;

-- Postes de coût détaillés, pour afficher le calcul sans le refaire côté front
alter table public.annonces add column if not exists travaux       numeric;
alter table public.annonces add column if not exists notaire       numeric;
alter table public.annonces add column if not exists portage       numeric;
alter table public.annonces add column if not exists frais_revente numeric;
alter table public.annonces add column if not exists prix_revente  numeric;
alter table public.annonces add column if not exists cout_total    numeric;

-- melo_id devient inutile mais on ne le supprime pas : il porte l'historique
-- des annonces collectées avant la bascule.
comment on column public.annonces.melo_id is
  'Obsolète depuis la bascule vers le sourcing mail. Conservé pour historique.';

create index if not exists idx_annonces_empreinte on public.annonces (empreinte);
create index if not exists idx_annonces_dashboard
  on public.annonces (zone, actif, principal, score desc);

-- ── Journal des alertes envoyées ────────────────────────────────────────────
-- Évite de renvoyer une alerte Telegram à chaque cycle pour la même annonce.
create table if not exists public.alertes_envoyees (
  id          bigserial primary key,
  annonce_id  text not null,
  score       integer,
  envoye_le   timestamptz not null default now()
);

create unique index if not exists idx_alertes_annonce
  on public.alertes_envoyees (annonce_id);

-- ── Sécurité : verrouillage des écritures ───────────────────────────────────
-- La clé anon est publique (elle est dans le bundle du front et sur GitHub).
-- Sans ces règles, n'importe qui peut vider la base.

alter table public.annonces          enable row level security;
alter table public.feedbacks         enable row level security;
alter table public.historique_prix   enable row level security;
alter table public.alertes_envoyees  enable row level security;

-- Le dashboard lit les annonces et leur historique.
drop policy if exists anon_lecture_annonces on public.annonces;
create policy anon_lecture_annonces on public.annonces
  for select to anon using (true);

drop policy if exists anon_lecture_historique on public.historique_prix;
create policy anon_lecture_historique on public.historique_prix
  for select to anon using (true);

-- Le dashboard écrit uniquement ses feedbacks like/dislike.
drop policy if exists anon_lecture_feedbacks on public.feedbacks;
create policy anon_lecture_feedbacks on public.feedbacks
  for select to anon using (true);

drop policy if exists anon_insertion_feedbacks on public.feedbacks;
create policy anon_insertion_feedbacks on public.feedbacks
  for insert to anon with check (true);

drop policy if exists anon_suppression_feedbacks on public.feedbacks;
create policy anon_suppression_feedbacks on public.feedbacks
  for delete to anon using (true);

-- Aucune policy d'écriture sur annonces pour anon : seul le worker,
-- qui utilise la clé service_role, peut insérer et mettre à jour.
--
-- Conséquence à connaître : le bouton corbeille du dashboard passait par
-- update annonces.actif = false avec la clé anon. Il ne fonctionnera plus.
-- Le masquage se fait désormais côté front à partir des dislikes enregistrés
-- dans feedbacks, ce qui est de toute façon plus propre : une annonce écartée
-- reste en base et continue d'alimenter le scoring ML.

-- ── Reprise des données existantes ──────────────────────────────────────────
update public.annonces set principal = true where principal is null;
