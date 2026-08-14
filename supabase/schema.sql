create table if not exists interview_sessions (
  id uuid primary key default gen_random_uuid(),
  job_posting text not null,
  questions jsonb not null,
  rubric jsonb not null,
  transcript text,
  scorecard jsonb,
  status text not null default 'pending' check (status in ('pending', 'scored')),
  created_at timestamptz not null default now()
);

alter table interview_sessions enable row level security;

-- Frontend (publishable key) can only read. All writes go through n8n's
-- secret key, which bypasses RLS entirely — so no insert/update policy needed.
-- Note: this policy has no `to` clause, so it grants read access to every
-- role, including anyone holding the publishable key embedded in the shipped
-- page. Accepted for this single-user local tool per the plan's scope — do
-- not host this publicly without tightening it.
drop policy if exists "Allow anon read" on interview_sessions;
create policy "Allow anon read" on interview_sessions
  for select
  using (true);

do $$ begin
  if not exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime' and tablename = 'interview_sessions'
  ) then
    alter publication supabase_realtime add table interview_sessions;
  end if;
end $$;
