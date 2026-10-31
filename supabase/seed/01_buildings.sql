-- 01_buildings: the fictional campus for the Pulse map (P4.3). Codes A–M without I/J
-- (11 buildings); map_x/map_y on a 1000×600 SVG grid. Names are generic, not real GJU buildings.
-- Idempotent: re-running updates names and coordinates in place.

insert into public.buildings (id, code, name_en, name_ar, map_x, map_y) values
  ('A', 'A', 'Administration',            'مبنى الإدارة',              120, 110),
  ('B', 'B', 'Business School',           'كلية الأعمال',              300,  90),
  ('C', 'C', 'Computing',                 'كلية الحوسبة',              480, 120),
  ('D', 'D', 'Design Studios',            'استوديوهات التصميم',        660,  90),
  ('E', 'E', 'Engineering Labs',          'مختبرات الهندسة',           840, 130),
  ('F', 'F', 'Finance and Registration',  'المالية والتسجيل',          150, 300),
  ('G', 'G', 'Guest and Student Center',  'مركز الطلبة والزوار',       360, 290),
  ('H', 'H', 'Health Clinic',             'العيادة الصحية',            560, 310),
  ('K', 'K', 'Knowledge Library',         'المكتبة',                   760, 300),
  ('L', 'L', 'Lecture Halls',             'قاعات المحاضرات',           260, 480),
  ('M', 'M', 'Main Teaching Building',    'المبنى التعليمي الرئيسي',   620, 480)
on conflict (id) do update set
  code = excluded.code, name_en = excluded.name_en, name_ar = excluded.name_ar,
  map_x = excluded.map_x, map_y = excluded.map_y;
