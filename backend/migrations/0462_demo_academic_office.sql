-- Checkpoint E (TE46-5): a demo database seeded before Task 46 has no academic office, so its certificate, transcript
-- and instalment requests (the academic office's first steps) had nobody to act. As the seed does now, the demo's dean's
-- office also holds the academic office. Only a demo database (it has the demo logins); a prod database is not touched.
INSERT OR IGNORE INTO role_grants(user_id, role, granted_at)
  SELECT u.id, 'academic_office', strftime('%Y-%m-%dT%H:%M:%S', 'now') FROM users u
  WHERE u.role = 'office' AND EXISTS (SELECT 1 FROM settings WHERE key = 'demo_logins')
    AND NOT EXISTS (SELECT 1 FROM role_grants g WHERE g.user_id = u.id AND g.role = 'academic_office');
