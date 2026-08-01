INSERT INTO vehicle_recalls (
    nhtsa_campaign_number,
    component,
    vehicle_tag,
    chunk_text,
    chunk_source,
    embedding
)
VALUES %s;

