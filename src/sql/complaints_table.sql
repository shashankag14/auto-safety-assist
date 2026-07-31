CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS vehicle_complaints(
    id SERIAL PRIMARY KEY,
    odi_number INT,
    components VARCHAR(256),
    crash BOOLEAN,
    fire BOOLEAN,
    vehicle_tag VARCHAR(64),
    summary TEXT,
    embedding vector(384)
);