-- 01_buildings: the fictional campus for the Pulse map (P4.3). Codes A–M without I/J
-- (11 buildings); map_x/map_y on a 1000×600 SVG grid. Only L is named (the library); the others are letters only (2026-11-09).
-- Idempotent: re-running updates names and coordinates in place.

insert into public.buildings (id, code, name_en, name_ar, map_x, map_y) values
  ('A', 'A', '',        '',        120, 110),
  ('B', 'B', '',        '',        300,  90),
  ('C', 'C', '',        '',        480, 120),
  ('D', 'D', '',        '',        660,  90),
  ('E', 'E', '',        '',        840, 130),
  ('F', 'F', '',        '',        150, 300),
  ('G', 'G', '',        '',        360, 290),
  ('H', 'H', '',        '',        560, 310),
  ('K', 'K', '',        '',        760, 300),
  ('L', 'L', 'Library', 'المكتبة', 260, 480),
  ('M', 'M', '',        '',        620, 480)
on conflict (id) do update set
  code = excluded.code, name_en = excluded.name_en, name_ar = excluded.name_ar,
  map_x = excluded.map_x, map_y = excluded.map_y;
