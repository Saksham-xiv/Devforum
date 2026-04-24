LEVEL_THRESHOLDS = [
    (360, "Expert"),
    (240, "Advanced"),
    (120, "Builder"),
    (60, "Learner"),
    (0, "Beginner"),
]


def level_from_points(points):
    total = int(points or 0)
    for threshold, label in LEVEL_THRESHOLDS:
        if total >= threshold:
            return label
    return "Beginner"


def sync_user_progress(cursor, user_id):
    cursor.execute(
        """
        SELECT COALESCE(SUM(problem_sets.points), 0) AS solve_points
        FROM solved_problems
        JOIN problem_sets ON problem_sets.id = solved_problems.problem_id
        WHERE solved_problems.user_id = %s
        """,
        (user_id,),
    )
    solve_row = cursor.fetchone()
    solve_points = int((solve_row["solve_points"] if isinstance(solve_row, dict) else solve_row[0]) or 0)

    cursor.execute(
        """
        SELECT COUNT(*) AS joined_count
        FROM community_members
        WHERE user_id = %s
        """,
        (user_id,),
    )
    community_row = cursor.fetchone()
    joined_count = int((community_row["joined_count"] if isinstance(community_row, dict) else community_row[0]) or 0)

    experience_points = solve_points + (joined_count * 15)
    level_name = level_from_points(experience_points)

    cursor.execute(
        """
        UPDATE users
        SET experience_points = %s,
            level_name = %s
        WHERE id = %s
        """,
        (experience_points, level_name, user_id),
    )

    return {
        "solve_points": solve_points,
        "joined_communities": joined_count,
        "experience_points": experience_points,
        "level_name": level_name,
    }
