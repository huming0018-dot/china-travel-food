-- 聚合及候选由后台管理；浏览器不得直接改写入库结果。
alter table public.crowd_store_evidence enable row level security;
alter table public.crowd_store_candidates enable row level security;
revoke all on public.crowd_store_evidence, public.crowd_store_candidates from public, anon, authenticated;
grant all on public.crowd_store_evidence, public.crowd_store_candidates to service_role;
revoke all on sequence public.crowd_store_candidates_id_seq from public, anon, authenticated;
grant usage, select on sequence public.crowd_store_candidates_id_seq to service_role;

