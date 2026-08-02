CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS vehicle_complaints(
    id SERIAL PRIMARY KEY,
    update_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    odi_number INT NOT NULL,
    components VARCHAR(256) NOT NULL,
    crash BOOLEAN,
    fire BOOLEAN,
    vehicle_tag VARCHAR(64) NOT NULL,
    summary TEXT NOT NULL,
    embedding vector(384) NOT NULL
);



DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'vehicle_complaints_odi_key') THEN
        ALTER TABLE vehicle_complaints
        ADD CONSTRAINT vehicle_complaints_odi_key
        UNIQUE (odi_number);
    END IF;
END $$;