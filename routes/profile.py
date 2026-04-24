from flask import Blueprint, jsonify, current_app, request, url_for
from flask_jwt_extended import jwt_required, get_jwt_identity
from utils.avatar import (
    ALLOWED_AVATAR_EXTENSIONS,
    find_avatar_filename,
    save_avatar,
)

profile_bp = Blueprint("profile", __name__)


def build_avatar_url(user_id):
    avatar_filename = find_avatar_filename(current_app, user_id)
    if not avatar_filename:
        return None
    return url_for(
        "static",
        filename=f"uploads/avatars/{avatar_filename}",
        _external=True,
    )

@profile_bp.route("/leaderboard", methods=["GET"])
def leaderboard():
    conn = current_app.get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, username, reputation, experience_points, level_name
        FROM users
        ORDER BY reputation DESC, experience_points DESC
        LIMIT 10
    """)

    users = cursor.fetchall()

    cursor.close()
    conn.close()

    for user in users:
        user["avatar_url"] = build_avatar_url(user["id"])

    return jsonify(users)

@profile_bp.route("/", methods=["GET"])
@jwt_required()
def get_profile():
    user_id = int(get_jwt_identity())

    conn = current_app.get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT username, reputation, experience_points, level_name
        FROM users
        WHERE id = %s
    """, (user_id,))
    user = cursor.fetchone()

    cursor.execute("""
        SELECT COUNT(*) AS total_posts
        FROM posts
        WHERE user_id = %s
    """, (user_id,))
    posts = cursor.fetchone()

    cursor.execute("""
        SELECT COUNT(*) AS total_comments
        FROM comments
        WHERE user_id = %s
    """, (user_id,))
    comments = cursor.fetchone()

    cursor.execute("""
        SELECT COUNT(*) AS accepted_answers
        FROM comments
        WHERE user_id = %s AND is_accepted = TRUE
    """, (user_id,))
    accepted = cursor.fetchone()

    cursor.execute("""
        SELECT COUNT(*) AS solved_problems
        FROM solved_problems
        WHERE user_id = %s
    """, (user_id,))
    solved = cursor.fetchone()

    cursor.execute("""
        SELECT COUNT(*) AS joined_communities
        FROM community_members
        WHERE user_id = %s
    """, (user_id,))
    joined = cursor.fetchone()

    cursor.close()
    conn.close()

    return jsonify({
        "user_id": user_id,
        "username": user["username"],
        "reputation": user["reputation"],
        "experience_points": user.get("experience_points", 0),
        "level_name": user.get("level_name", "Beginner"),
        "total_posts": posts["total_posts"],
        "total_comments": comments["total_comments"],
        "accepted_answers": accepted["accepted_answers"],
        "solved_problems": solved["solved_problems"],
        "joined_communities": joined["joined_communities"],
        "avatar_url": build_avatar_url(user_id)
    })

@profile_bp.route("/badges", methods=["GET"])
@jwt_required()
def get_badges():
    user_id = int(get_jwt_identity())

    conn = current_app.get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT badge_name FROM badges WHERE user_id = %s",
        (user_id,)
    )

    badges = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(badges)


@profile_bp.route("/avatar", methods=["POST"])
@jwt_required()
def upload_avatar():
    user_id = int(get_jwt_identity())
    uploaded_file = request.files.get("avatar")

    if not uploaded_file or not uploaded_file.filename:
        return jsonify({"error": "Avatar file is required"}), 400

    try:
        save_avatar(current_app, user_id, uploaded_file)
    except ValueError:
        allowed_types = ", ".join(sorted(ALLOWED_AVATAR_EXTENSIONS))
        return jsonify(
            {"error": f"Unsupported file type. Use: {allowed_types}"}
        ), 400

    return jsonify({
        "message": "Avatar updated successfully",
        "avatar_url": build_avatar_url(user_id)
    })
