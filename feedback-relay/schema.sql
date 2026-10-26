CREATE TABLE reports (
  id TEXT PRIMARY KEY,
  payload TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  state TEXT NOT NULL DEFAULT 'reserved',
  reference TEXT
);
