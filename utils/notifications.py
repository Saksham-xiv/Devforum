def create_notification(
    cursor,
    user_id,
    notification_type,
    title,
    message_body,
    related_problem_id=None,
    related_post_id=None,
    related_community_id=None,
):
    cursor.execute(
        """
        INSERT INTO user_notifications (
            user_id,
            notification_type,
            title,
            message_body,
            related_problem_id,
            related_post_id,
            related_community_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            user_id,
            notification_type,
            title,
            message_body,
            related_problem_id,
            related_post_id,
            related_community_id,
        ),
    )
