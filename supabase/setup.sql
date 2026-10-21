begin;

create table public.training_logs (
  user_id uuid primary key references auth.users(id) on delete cascade,
  data jsonb not null default '{"logs":[],"checkins":{},"settings":{"calorieGoals":[]}}'::jsonb,
  revision bigint not null default 0 check (revision >= 0),
  constraint data_is_object check (jsonb_typeof(data) = 'object')
);

alter table public.training_logs enable row level security;

revoke all on table public.training_logs from public, anon, authenticated;
grant select, insert, update on table public.training_logs to authenticated;

create policy "Read own logs"
on public.training_logs for select to authenticated
using ((select auth.uid()) = user_id);

create policy "Create own logs"
on public.training_logs for insert to authenticated
with check ((select auth.uid()) = user_id);

create policy "Update own logs"
on public.training_logs for update to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

commit;
