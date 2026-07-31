CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS vehicle_recalls (
    id SERIAL PRIMARY KEY,
    nhtsa_campaign_number VARCHAR(64),
    component VARCHAR(256),
    vehicle_tag VARCHAR(64),
    chunk_text TEXT,
    chunk_source VARCHAR(64),
    embedding vector(384)
);
