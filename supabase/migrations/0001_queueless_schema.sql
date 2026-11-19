-- QueueLess — Supabase (PostgreSQL) schema, migration 0001
-- Run in: Supabase Dashboard > SQL Editor, or `supabase db push`.
-- The FastAPI backend connects with the Postgres connection string (role `postgres`),
-- which bypasses RLS. RLS is enabled below with NO policies, so the public
-- Supabase REST/GraphQL API (anon / authenticated roles) can read or write nothing.

begin;

-- ---------------------------------------------------------------- enums ----
create type user_role       as enum ('customer', 'staff', 'admin');
create type service_status  as enum ('active', 'paused', 'archived');
create type counter_status  as enum ('open', 'closed', 'unavailable');
create type staff_availability as enum ('available', 'busy', 'off');
create type priority_type   as enum ('none', 'senior', 'disabled', 'pregnant', 'emergency');
create type token_status    as enum (
  'booked', 'confirmed', 'waiting', 'approaching',
  'called', 'serving', 'completed', 'cancelled', 'no_show'
);
create type delivery_status as enum ('pending', 'sent', 'failed', 'read');

-- ------------------------------------------------------------ locations ----
-- v1 runs a single location; the column exists so multi-location is additive.
create table locations (
  location_id bigint generated always as identity primary key,
  name        text not null,
  timezone    text not null default 'Asia/Kolkata',
  created_at  timestamptz not null default now()
);

create table location_settings (
  location_id bigint not null references locations(location_id) on delete cascade,
  key         text   not null,
  value       jsonb  not null,
  updated_at  timestamptz not null default now(),
  updated_by  bigint,
  primary key (location_id, key)
);

-- ---------------------------------------------------------------- users ----
create table users (
  user_id       bigint generated always as identity primary key,
  name          text not null check (length(name) between 1 and 120),
  email         text not null,
  phone         text,
  password_hash text not null,
  role          user_role not null default 'customer',
  is_demo       boolean not null default false,
  created_at    timestamptz not null default now()
);
create unique index users_email_lower_uq on users (lower(email));

create table push_devices (
  device_id  bigint generated always as identity primary key,
  user_id    bigint not null references users(user_id) on delete cascade,
  fcm_token  text not null unique,
  created_at timestamptz not null default now()
);
create index push_devices_user_idx on push_devices (user_id);

-- ------------------------------------------------------------- services ----
create table services (
  service_id               bigint generated always as identity primary key,
  location_id              bigint not null references locations(location_id),
  service_name             text not null,
  code                     text not null check (length(code) between 1 and 3), -- token prefix, e.g. "A"
  description              text,
  average_service_duration numeric(6,2) not null default 8 check (average_service_duration > 0), -- minutes
  status                   service_status not null default 'active',
  created_at               timestamptz not null default now(),
  unique (location_id, code),
  unique (location_id, service_name)
);

-- ---------------------------------------------------------------- staff ----
create table staff (
  staff_id     bigint generated always as identity primary key,
  user_id      bigint not null unique references users(user_id) on delete cascade,
  availability staff_availability not null default 'available'
);

-- ------------------------------------------------------------- counters ----
create table counters (
  counter_id        bigint generated always as identity primary key,
  location_id       bigint not null references locations(location_id),
  counter_name      text not null,
  status            counter_status not null default 'closed',
  assigned_staff_id bigint references staff(staff_id) on delete set null,
  created_at        timestamptz not null default now(),
  unique (location_id, counter_name)
);
-- one staff member can staff at most one counter at a time
create unique index counters_staff_uq on counters (assigned_staff_id) where assigned_staff_id is not null;

create table counter_services (
  counter_id bigint not null references counters(counter_id) on delete cascade,
  service_id bigint not null references services(service_id) on delete cascade,
  primary key (counter_id, service_id)
);
create index counter_services_service_idx on counter_services (service_id);

-- --------------------------------------------------------- queue tokens ----
create table queue_tokens (
  token_id       bigint generated always as identity primary key,
  user_id        bigint not null references users(user_id),
  service_id     bigint not null references services(service_id),
  counter_id     bigint references counters(counter_id),
  queue_date     date   not null,
  token_number   integer not null check (token_number > 0),      -- per service per day
  token_label    text not null,                                  -- e.g. "A-012"
  queue_position integer,                                        -- 1-based, among waiting tokens; null once called
  priority_type  priority_type not null default 'none',
  status         token_status  not null default 'booked',
  is_demo        boolean not null default false,
  created_at     timestamptz not null default now(),             -- = queue entry time
  arrival_time   timestamptz,                                    -- physical check-in
  unique (service_id, queue_date, token_number)
);
-- Duplicate-booking protection: one active token per user per service.
create unique index queue_tokens_one_active_uq
  on queue_tokens (user_id, service_id)
  where status in ('booked','confirmed','waiting','approaching','called','serving');
create index queue_tokens_service_status_idx on queue_tokens (service_id, status);
create index queue_tokens_user_idx           on queue_tokens (user_id, created_at desc);
create index queue_tokens_created_idx        on queue_tokens (created_at);

-- Append-only event log (never update/delete rows).
create table queue_events (
  event_id      bigint generated always as identity primary key,
  token_id      bigint not null references queue_tokens(token_id) on delete cascade,
  event_type    text   not null,
  actor_user_id bigint references users(user_id),
  timestamp     timestamptz not null default now(),
  metadata      jsonb not null default '{}'::jsonb
);
create index queue_events_token_idx on queue_events (token_id, timestamp);
create index queue_events_type_idx  on queue_events (event_type, timestamp);

create table service_records (
  record_id             bigint generated always as identity primary key,
  token_id              bigint not null unique references queue_tokens(token_id) on delete cascade,
  counter_id            bigint not null references counters(counter_id),
  service_start_time    timestamptz not null,
  service_end_time      timestamptz,
  actual_service_duration numeric(8,2),   -- minutes
  actual_wait_minutes   numeric(8,2),     -- service_start - token.created_at (see PRD §4)
  rating                smallint check (rating between 1 and 5),
  check (service_end_time is null or service_end_time >= service_start_time)
);
create index service_records_counter_idx on service_records (counter_id, service_start_time);
create index service_records_start_idx   on service_records (service_start_time);

-- ---------------------------------------------------------- predictions ----
create table predictions (
  prediction_id          bigint generated always as identity primary key,
  token_id               bigint not null references queue_tokens(token_id) on delete cascade,
  predicted_waiting_time numeric(8,2) not null,   -- minutes
  prediction_lower_bound numeric(8,2),            -- null when method = 'fallback'
  prediction_upper_bound numeric(8,2),
  method                 text not null check (method in ('ml','fallback')),
  model_version          text not null,           -- 'fallback-v1' for non-ML
  features               jsonb,                   -- snapshot for drift analysis / retraining audit
  prediction_timestamp   timestamptz not null default now()
);
create index predictions_token_idx on predictions (token_id, prediction_timestamp desc);

create table demand_forecasts (
  forecast_id       bigint generated always as identity primary key,
  service_id        bigint not null references services(service_id) on delete cascade,
  interval_start    timestamptz not null,
  horizon_minutes   integer not null check (horizon_minutes in (30, 60, 120)),
  predicted_arrivals numeric(8,2) not null,
  actual_arrivals   integer,          -- back-filled once the interval has passed
  method            text not null default 'ml',
  model_version     text not null,
  created_at        timestamptz not null default now(),
  unique (service_id, interval_start, horizon_minutes, model_version)
);

-- --------------------------------------------------------- notifications ----
create table notifications (
  notification_id   bigint generated always as identity primary key,
  user_id           bigint not null references users(user_id) on delete cascade,
  token_id          bigint references queue_tokens(token_id) on delete set null,
  notification_type text not null,
  title             text not null,
  message           text not null,
  delivery_status   delivery_status not null default 'pending',
  read_at           timestamptz,
  created_at        timestamptz not null default now()
);
create index notifications_user_idx on notifications (user_id, created_at desc);

-- ------------------------------------------------------------ audit/ops ----
create table audit_logs (
  audit_id      bigint generated always as identity primary key,
  actor_user_id bigint references users(user_id),
  action        text not null,
  entity_type   text not null,
  entity_id     bigint,
  details       jsonb not null default '{}'::jsonb,
  created_at    timestamptz not null default now()
);
create index audit_logs_created_idx on audit_logs (created_at desc);
create index audit_logs_entity_idx  on audit_logs (entity_type, entity_id);

create table special_events (
  event_date  date not null,
  location_id bigint not null references locations(location_id) on delete cascade,
  label       text not null,
  is_holiday  boolean not null default false,
  primary key (location_id, event_date)
);

-- ------------------------------------------------------------------ RLS ----
-- Locked down by default: no policies => anon/authenticated roles see nothing.
do $$
declare t text;
begin
  for t in select unnest(array[
    'locations','location_settings','users','push_devices','services','staff','counters',
    'counter_services','queue_tokens','queue_events','service_records','predictions',
    'demand_forecasts','notifications','audit_logs','special_events'
  ]) loop
    execute format('alter table public.%I enable row level security', t);
  end loop;
end $$;

commit;
