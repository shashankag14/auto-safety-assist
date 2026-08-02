CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS vehicle_recalls (
    id SERIAL PRIMARY KEY,
    update_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    nhtsa_campaign_number VARCHAR(64) NOT NULL,
    component VARCHAR(256) NOT NULL,
    vehicle_tag VARCHAR(64) NOT NULL,
    chunk_text TEXT NOT NULL,
    chunk_source VARCHAR(64) NOT NULL,
    embedding vector(384) NOT NULL
);


DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'vehicle_recalls_campaign_source_key') THEN
        ALTER TABLE vehicle_recalls
        ADD CONSTRAINT vehicle_recalls_campaign_source_key
        UNIQUE (nhtsa_campaign_number, chunk_source);
    END IF;
END $$;