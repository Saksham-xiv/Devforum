from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity

admin_bp = Blueprint("admin", __name__)

# Helper function to check admin
def is_admin():
    conn = current_app.get_db_connection()
    cursor = conn.cursor()

    user_id = get_jwt_identity()
    cursor.execute("SELECT role FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()

    cursor.close()
    conn.close()

    return user and user["role"] == "admin"


# View all reports (Admin only)
@admin_bp.route("/reports", methods=["GET"])
@jwt_required()
def view_reports():
    if not is_admin():
        return jsonify({"error": "Admin access required"}), 403

    conn = current_app.get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT reports.id,
           reports.reason,
           reports.status,
           reports.created_at,
           users.username AS reported_by,
           reports.post_id,
           reports.comment_id
        FROM reports
        JOIN users ON reports.reporter_id = users.id
        ORDER BY reports.created_at DESC
        """)

    reports = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(reports)


# Delete comment (Admin only)
@admin_bp.route("/delete/comment/<int:comment_id>", methods=["DELETE"])
@jwt_required()
def delete_comment(comment_id):
    if not is_admin():
        return jsonify({"error": "Admin access required"}), 403

    conn = current_app.get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM comments WHERE id = %s", (comment_id,))
    conn.commit()

    cursor.close()
    conn.close()

    return jsonify({"message": "Comment deleted"})
