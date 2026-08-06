INSERT INTO vehicle_recalls (
    nhtsa_campaign_number,
    component,
    vehicle_tag,
    chunk_text,
    chunk_source,
    embedding
)
VALUES %s
ON CONFLICT (nhtsa_campaign_number, chunk_source)
DO UPDATE SET
    update_timestamp = NOW(),
    component = EXCLUDED.component,
    vehicle_tag = EXCLUDED.vehicle_tag,
    chunk_text = EXCLUDED.chunk_text,
    embedding = EXCLUDED.embedding;