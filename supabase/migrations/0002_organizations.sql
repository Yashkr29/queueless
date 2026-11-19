-- QueueLess — migration 0002: organizations (hospital, college, bank, government office, ...)
-- Locations become first-class: each has a type, address, active flag; staff belong to one location.
begin;

alter table locations add column location_type text not null default 'other'
  check (location_type in ('hospital', 'college', 'bank', 'government', 'other'));
alter table locations add column address   text;
alter table locations add column is_active boolean not null default true;

alter table staff add column location_id bigint references locations(location_id);
update staff set location_id = (select min(location_id) from locations) where location_id is null;
create index staff_location_idx on staff (location_id);

commit;
