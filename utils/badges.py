def check_and_award_badges(cursor, user_id):

    # ============================
    # GET USER REPUTATION
    # ============================
    cursor.execute("SELECT reputation FROM users WHERE id = %s", (user_id,))
    rep_data = cursor.fetchone()

    if not rep_data:
        return

    rep = rep_data["reputation"] if isinstance(rep_data, dict) else rep_data[0]

    badges = []

    # ============================
    # 🏆 REPUTATION BADGES
    # ============================
    if rep >= 10:
        badges.append("Beginner")
    if rep >= 50:
        badges.append("Contributor")
    if rep >= 100:
        badges.append("Expert")

    # ============================
    # 💬 ACTIVITY BADGES
    # ============================

    # First Answer
    cursor.execute("SELECT COUNT(*) AS total FROM comments WHERE user_id = %s", (user_id,))
    result = cursor.fetchone()
    total_comments = result["total"] if isinstance(result, dict) else result[0]

    if total_comments >= 1:
        badges.append("First Answer")

    # Accepted Answer
    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM comments 
        WHERE user_id = %s AND is_accepted = TRUE
    """, (user_id,))
    result = cursor.fetchone()
    accepted = result["total"] if isinstance(result, dict) else result[0]

    if accepted >= 1:
        badges.append("Accepted Answer")

    # Helpful (5 upvotes)
    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM votes
        WHERE comment_id IN (
            SELECT id FROM comments WHERE user_id = %s
        ) AND vote_type = 'upvote'
    """, (user_id,))
    result = cursor.fetchone()
    upvotes = result["total"] if isinstance(result, dict) else result[0]

    if upvotes >= 5:
        badges.append("Helpful")

    # ============================
    # INSERT BADGES
    # ============================
    for badge in badges:
        try:
            cursor.execute(
                """
                INSERT INTO badges (user_id, badge_name)
                VALUES (%s, %s)
                ON CONFLICT (user_id, badge_name) DO NOTHING
                """,
                (user_id, badge)
            )
        except Exception as e:
            print("Badge insert error:", e)
