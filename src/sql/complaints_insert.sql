INSERT INTO vehicle_complaints (
    odi_number,
    components,
    crash,
    fire,
    vehicle_tag,
    summary,
    embedding
)
VALUES %s
ON CONFLICT (odi_number)
DO UPDATE SET
    update_timestamp = NOW(),
    components = EXCLUDED.components,
    crash = EXCLUDED.crash,
    fire = EXCLUDED.fire,
    vehicle_tag = EXCLUDED.vehicle_tag,
    summary = EXCLUDED.summary,
    embedding = EXCLUDED.embedding;