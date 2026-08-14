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

-- Frontend (anon key) can only read. All writes go through n8n's service_role key,
-- which bypasses RLS entirely — so no insert/update policy is needed here.
create policy "Allow anon read" on interview_sessions
  for select
  using (true);

alter publication supabase_realtime add table interview_sessions;
