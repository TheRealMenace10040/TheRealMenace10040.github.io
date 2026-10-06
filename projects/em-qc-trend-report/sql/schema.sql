-- Environmental monitoring schema (SQLite / PostgreSQL compatible)
CREATE TABLE limits (
    sample_type   TEXT PRIMARY KEY,
    alert_limit   INTEGER NOT NULL,
    action_limit  INTEGER NOT NULL
);
CREATE TABLE em_samples (
    sample_id    TEXT PRIMARY KEY,
    sample_date  DATE NOT NULL,
    room         TEXT NOT NULL,
    iso_class    TEXT NOT NULL,
    sample_type  TEXT NOT NULL REFERENCES limits(sample_type),
    cfu          INTEGER NOT NULL CHECK (cfu >= 0),
    analyst      TEXT
);
CREATE INDEX ix_em_date ON em_samples(sample_date);
CREATE INDEX ix_em_room ON em_samples(room, sample_type);
