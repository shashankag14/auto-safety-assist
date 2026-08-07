SELECT * FROM (
    SELECT 'recall' AS source, id, vehicle_tag, chunk_text AS TEXT, 1-(embedding <=> %s) AS cosine_sim
    FROM vehicle_recalls
    UNION ALL
    SELECT 'complaint' AS source, id, vehicle_tag, summary AS TEXT, 1-(embedding <=> %s) AS cosine_sim
    FROM vehicle_complaints

) combined
    ORDER BY cosine_sim DESC
    LIMIT %s;