from flask import Blueprint, current_app, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required

notifications_bp = Blueprint("notifications", __name__)


@notifications_bp.route("/", methods=["GET"])
@jwt_required()
def get_notifications():
    user_id = int(get_jwt_identity())
    conn = current_app.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, notification_type, title, message_body, created_at, is_read
        FROM user_notifications
        WHERE user_id = %s
        ORDER BY created_at DESC, id DESC
        LIMIT 6
        """,
        (user_id,),
    )
    notifications = [
        {
            "id": row["id"],
            "type": row["notification_type"],
            "title": row["title"],
            "text": row["message_body"],
            "time": row["created_at"].strftime("%Y-%m-%d %H:%M"),
            "is_read": bool(row["is_read"]),
        }
        for row in cursor.fetchall()
    ]
    cursor.close()
    conn.close()
    return jsonify(notifications)
