from flask import Blueprint, jsonify, current_app

users_bp = Blueprint("users", __name__)

@users_bp.route("/leaderboard", methods=["GET"])
def leaderboard():
    conn = current_app.get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT username, reputation
        FROM users
        ORDER BY reputation DESC
    """)

    users = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(users)

@users_bp.route("/profile/<string:username>", methods=["GET"])
def user_profile(username):
    conn = current_app.get_db_connection()
    cursor = conn.cursor()

    # Get basic user info
    cursor.execute("""
        SELECT id, username, reputation
        FROM users
        WHERE username = %s
    """, (username,))
    user = cursor.fetchone()

    if not user:
        return jsonify({"error": "User not found"}), 404

    user_id = user["id"]

    # Count posts
    cursor.execute("SELECT COUNT(*) AS total_posts FROM posts WHERE user_id = %s", (user_id,))
    total_posts = cursor.fetchone()["total_posts"]

    # Count comments
    cursor.execute("SELECT COUNT(*) AS total_comments FROM comments WHERE user_id = %s", (user_id,))
    total_comments = cursor.fetchone()["total_comments"]

    # Count votes received on user's comments
    cursor.execute("""
        SELECT 
            SUM(CASE WHEN vote_type = 'upvote' THEN 1 ELSE 0 END) AS upvotes_received,
            SUM(CASE WHEN vote_type = 'downvote' THEN 1 ELSE 0 END) AS downvotes_received
        FROM votes
        JOIN comments ON votes.comment_id = comments.id
        WHERE comments.user_id = %s
    """, (user_id,))

    vote_data = cursor.fetchone()

    profile_data = {
        "username": user["username"],
        "reputation": user["reputation"],
        "total_posts": total_posts,
        "total_comments": total_comments,
        "total_upvotes_received": int(vote_data["upvotes_received"] or 0),
        "total_downvotes_received": int(vote_data["downvotes_received"] or 0)
    }

    cursor.close()
    conn.close()

    return jsonify(profile_data)
