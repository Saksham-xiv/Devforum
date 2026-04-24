from flask import Blueprint, request, jsonify, current_app, url_for
from flask_jwt_extended import jwt_required, get_jwt_identity
from utils.avatar import find_avatar_filename

posts_bp = Blueprint("posts", __name__)


def build_avatar_url(user_id):
    avatar_filename = find_avatar_filename(current_app, user_id)
    if not avatar_filename:
        return None
    return url_for(
        "static",
        filename=f"uploads/avatars/{avatar_filename}",
        _external=True,
    )

# ==============================
# ✅ CREATE POST
# ==============================
@posts_bp.route("/", methods=["POST"])
@jwt_required()
def create_post():
    data = request.get_json()
    user_id = int(get_jwt_identity())
    title = data.get("title")
    content = data.get("content")
    community_id = data.get("community_id")
    post_type = data.get("post_type") or "discussion"

    if not title or not content:
        return jsonify({"error": "Title and content required"}), 400

    conn = current_app.get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO posts (user_id, title, content, community_id, post_type)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (user_id, title, content, community_id, post_type)
    )

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"message": "Post created successfully"}), 201


# ==============================
# ✅ GET ALL POSTS
# ==============================
@posts_bp.route("/", methods=["GET"])
@jwt_required(optional=True)
def get_posts():
    conn = current_app.get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT posts.id,
               posts.user_id,
               posts.title,
               posts.content,
               posts.post_type,
               posts.community_id,
               posts.created_at,
               users.username,
               communities.name AS community_name
        FROM posts
        JOIN users ON posts.user_id = users.id
        LEFT JOIN communities ON posts.community_id = communities.id
        ORDER BY posts.created_at DESC
    """)

    posts = cursor.fetchall()

    cursor.close()
    conn.close()

    for post in posts:
        post["avatar_url"] = build_avatar_url(post["user_id"])

    return jsonify(posts)


# ==============================
# ✅ TRENDING POSTS
# ==============================
@posts_bp.route("/trending", methods=["GET"])
def trending_posts():
    conn = current_app.get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            posts.id,
            posts.user_id,
            posts.title,
            posts.created_at,
            users.username,
            COALESCE(SUM(
                CASE 
                    WHEN votes.vote_type = 'upvote' THEN 1
                    WHEN votes.vote_type = 'downvote' THEN -1
                    ELSE 0
                END
            ), 0) AS total_score,
            FLOOR(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - posts.created_at)) / 3600) AS age_hours
        FROM posts
        JOIN users ON posts.user_id = users.id
        LEFT JOIN comments ON comments.post_id = posts.id
        LEFT JOIN votes ON votes.comment_id = comments.id
        GROUP BY posts.id, posts.user_id, posts.title, posts.created_at, users.username
    """)

    posts = cursor.fetchall()

    # Apply trending formula
    for post in posts:
        score = int(post["total_score"] or 0)
        age = int(post["age_hours"] or 0)

        post["total_score"] = score
        post["age_hours"] = age
        post["trending_score"] = round(score / (age + 2), 4)
        post["avatar_url"] = build_avatar_url(post["user_id"])

    # Sort by trending score
    posts.sort(key=lambda x: x["trending_score"], reverse=True)

    cursor.close()
    conn.close()

    return jsonify(posts)


# ==============================
# ✅ REPORT POST
# ==============================
@posts_bp.route("/report/<int:post_id>", methods=["POST"])
@jwt_required()
def report_post(post_id):
    user_id = int(get_jwt_identity())
    data = request.get_json()
    reason = data.get("reason")

    if not reason:
        return jsonify({"error": "Reason required"}), 400

    conn = current_app.get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO reports (reporter_id, post_id, reason)
        VALUES (%s, %s, %s)
    """, (user_id, post_id, reason))

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"message": "Post reported successfully"})


# ==============================
# ✅ DELETE POST
# ==============================
@posts_bp.route("/<int:post_id>", methods=["DELETE"])
@jwt_required()
def delete_post(post_id):
    user_id = int(get_jwt_identity())

    conn = current_app.get_db_connection()
    cursor = conn.cursor()

    # Check if post belongs to user
    cursor.execute("SELECT user_id FROM posts WHERE id = %s", (post_id,))
    post = cursor.fetchone()

    if not post or int(post["user_id"]) != user_id:
        return jsonify({"error": "Unauthorized"}), 403

    # Delete comments first
    cursor.execute("DELETE FROM comments WHERE post_id = %s", (post_id,))

    cursor.execute("DELETE FROM posts WHERE id = %s", (post_id,))
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"message": "Post deleted"}), 200

