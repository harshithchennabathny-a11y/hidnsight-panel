def get_calibration_stats(conn):
    # Get all outcomes where rated_negative = 1
    # Group by interviewer_id, competency
    # Filter where count >= 3
    
    rows = conn.execute("""
        SELECT interviewer_id, competency, COUNT(*) as total_negative_ratings,
               SUM(CASE WHEN outcome = 'positive' THEN 1 ELSE 0 END) as positive_outcomes
        FROM outcomes
        WHERE rated_negative = 1
        GROUP BY interviewer_id, competency
        HAVING total_negative_ratings >= 3
    """).fetchall()
    
    results = []
    for r in rows:
        results.append({
            "interviewer_id": r["interviewer_id"],
            "competency": r["competency"],
            "total_negative_ratings": r["total_negative_ratings"],
            "positive_outcomes_when_rated_negative": r["positive_outcomes"],
            "disclosure": "Sample size is small. Synthetic data. Hired candidates only; rejected candidates have no outcomes."
        })
    return results
