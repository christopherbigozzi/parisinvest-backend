-- 004 — Repère de la Butte cité par l'annonce.
--
-- Le worker y écrit le terme qui a permis de situer le bien : une rue
-- (« lepic »), une station (« lamarck-caulaincourt »), un monument
-- (« sacre coeur ») ou le quartier lui-même (« montmartre »). Vide quand rien
-- dans l'annonce ne la situe — la localisation est alors invérifiable et le
-- score prend −20.
--
-- Le dashboard affiche le terme tel quel : « rue Lepic » et « Montmartre »
-- n'inspirent pas la même confiance, et c'est au lecteur d'en juger.

alter table public.annonces
  add column if not exists repere_butte text default '';

comment on column public.annonces.repere_butte is
  'Terme de la Butte cité par l''annonce (rue, station, monument). Vide quand rien ne situe le bien.';

create index if not exists idx_annonces_repere_butte
  on public.annonces (repere_butte)
  where repere_butte <> '';
