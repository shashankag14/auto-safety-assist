SELECT * FROM (
    SELECT 'recall' AS source, id, nhtsa_campaign_number AS external_id, vehicle_tag,
        chunk_text AS TEXT, 1-(embedding <=> %s) AS cosine_sim
    FROM vehicle_recalls
    UNION ALL
    SELECT 'complaint' AS source, id, odi_number::text AS external_id, vehicle_tag,
        summary AS TEXT, 1-(embedding <=> %s) AS cosine_sim
    FROM vehicle_complaints

) combined
    ORDER BY cosine_sim DESC
    LIMIT %s;