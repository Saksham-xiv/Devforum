from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from utils.badges import check_and_award_badges
from utils.notifications import create_notification

comments_bp = Blueprint("comments", __name__)


# ======================================
# ADD COMMENT (Answer)
# ======================================
@comments_bp.route("/<int:post_id>", methods=["POST"])
@jwt_required()
def add_comment(post_id):
    data = request.get_json()
    user_id = int(get_jwt_identity())
    content = data.get("content")

    if not content:
        return jsonify({"error": "Content required"}), 400

    conn = current_app.get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT user_id, title FROM posts WHERE id = %s", (post_id,))
    post = cursor.fetchone()
    if not post:
        cursor.close()
        conn.close()
        return jsonify({"error": "Post not found"}), 404

    cursor.execute(
        "INSERT INTO comments (post_id, user_id, content) VALUES (%s, %s, %s)",
        (post_id, user_id, content)
    )
    check_and_award_badges(cursor, user_id)

    if int(post["user_id"]) != user_id:
        create_notification(
            cursor,
            int(post["user_id"]),
            "reply",
            "New reply to your post",
            f"Someone replied to '{post['title']}'.",
            related_post_id=post_id,
        )

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"message": "Comment added successfully"}), 201


# ======================================
# GET COMMENTS FOR A POST
# ======================================
@comments_bp.route("/<int:post_id>", methods=["GET"])
def get_comments(post_id):
    conn = current_app.get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            comments.id,
            comments.content,
            comments.created_at,
            comments.is_accepted,
            users.username,
            SUM(CASE WHEN votes.vote_type = 'upvote' THEN 1 ELSE 0 END) AS upvotes,
            SUM(CASE WHEN votes.vote_type = 'downvote' THEN 1 ELSE 0 END) AS downvotes
        FROM comments
        JOIN users ON comments.user_id = users.id
        LEFT JOIN votes ON comments.id = votes.comment_id
        WHERE comments.post_id = %s
        GROUP BY comments.id, users.username
        ORDER BY comments.is_accepted DESC, comments.created_at DESC
    """, (post_id,))

    comments = cursor.fetchall()

    for comment in comments:
        comment["upvotes"] = int(comment["upvotes"] or 0)
        comment["downvotes"] = int(comment["downvotes"] or 0)
        comment["score"] = comment["upvotes"] - comment["downvotes"]

    cursor.close()
    conn.close()

    return jsonify(comments)


# ======================================
# ACCEPT ANSWER
# ======================================
@comments_bp.route("/accept/<int:comment_id>", methods=["POST"])
@jwt_required()
def accept_answer(comment_id):
    user_id = int(get_jwt_identity())

    conn = current_app.get_db_connection()
    cursor = conn.cursor()

    # Get comment + post info
    cursor.execute("""
        SELECT comments.id,
               comments.user_id AS answer_author,
               posts.user_id AS post_owner,
               posts.id AS post_id
        FROM comments
        JOIN posts ON comments.post_id = posts.id
        WHERE comments.id = %s
    """, (comment_id,))
    
    comment_data = cursor.fetchone()

    if not comment_data:
        cursor.close()
        conn.close()
        return jsonify({"error": "Comment not found"}), 404

    # Check ownership
    if int(comment_data["post_owner"]) != user_id:
        cursor.close()
        conn.close()
        return jsonify({"error": "Only post owner can accept answer"}), 403

    # Remove previously accepted answer for this post
    cursor.execute("""
        UPDATE comments
        SET is_accepted = FALSE
        WHERE post_id = %s
    """, (comment_data["post_id"],))

    # Mark this comment accepted
    cursor.execute("""
        UPDATE comments
        SET is_accepted = TRUE
        WHERE id = %s
    """, (comment_id,))

    # Mark post as resolved
    cursor.execute("""
        UPDATE posts
        SET is_resolved = TRUE
        WHERE id = %s
    """, (comment_data["post_id"],))

    # 🔥 Give +15 reputation to answer author
    cursor.execute("""
        UPDATE users
        SET reputation = reputation + 15
        WHERE id = %s
    """, (comment_data["answer_author"],))
    check_and_award_badges(cursor, comment_data["answer_author"])

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"message": "Answer accepted successfully"})


# ======================================
# VOTE ON COMMENT
# ======================================
@comments_bp.route("/vote/<int:comment_id>", methods=["POST"])
@jwt_required()
def vote_comment(comment_id):
    user_id = int(get_jwt_identity())
    data = request.get_json()
    vote_type = data.get("vote_type")

    if vote_type not in ["upvote", "downvote"]:
        return jsonify({"error": "Invalid vote type"}), 400

    conn = current_app.get_db_connection()
    cursor = conn.cursor()

    # Check comment exists
    cursor.execute("SELECT user_id FROM comments WHERE id = %s", (comment_id,))
    comment = cursor.fetchone()

    if not comment:
        cursor.close()
        conn.close()
        return jsonify({"error": "Comment not found"}), 404

    # Prevent self voting
    if int(comment["user_id"]) == user_id:
        cursor.close()
        conn.close()
        return jsonify({"error": "You cannot vote on your own comment"}), 403

    # Check existing vote
    cursor.execute(
        "SELECT vote_type FROM votes WHERE user_id = %s AND comment_id = %s",
        (user_id, comment_id)
    )
    existing_vote = cursor.fetchone()

    reputation_change = 0

    if existing_vote:
        if existing_vote["vote_type"] == vote_type:
            cursor.close()
            conn.close()
            return jsonify({"message": "Vote already exists"}), 200
        else:
            # Change vote
            cursor.execute(
                "UPDATE votes SET vote_type = %s WHERE user_id = %s AND comment_id = %s",
                (vote_type, user_id, comment_id)
            )
            reputation_change = 7 if vote_type == "upvote" else -7
    else:
        cursor.execute(
            "INSERT INTO votes (user_id, comment_id, vote_type) VALUES (%s, %s, %s)",
            (user_id, comment_id, vote_type)
        )
        reputation_change = 5 if vote_type == "upvote" else -2

    # Update comment author reputation
    cursor.execute(
        "UPDATE users SET reputation = reputation + %s WHERE id = %s",
        (reputation_change, comment["user_id"])
    )
    check_and_award_badges(cursor, comment["user_id"])

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"message": "Vote recorded successfully"})


# ======================================
# REPORT COMMENT
# ======================================
@comments_bp.route("/report/<int:comment_id>", methods=["POST"])
@jwt_required()
def report_comment(comment_id):
    user_id = int(get_jwt_identity())
    data = request.get_json()
    reason = data.get("reason")

    if not reason:
        return jsonify({"error": "Reason required"}), 400

    conn = current_app.get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO reports (reporter_id, comment_id, reason)
        VALUES (%s, %s, %s)
    """, (user_id, comment_id, reason))

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"message": "Comment reported successfully"})


# ======================================
# DELETE COMMENT
# ======================================
@comments_bp.route("/<int:comment_id>", methods=["DELETE"])
@jwt_required()
def delete_comment(comment_id):
    user_id = int(get_jwt_identity())

    conn = current_app.get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, user_id, post_id, is_accepted
        FROM comments
        WHERE id = %s
    """, (comment_id,))
    comment = cursor.fetchone()

    if not comment:
        cursor.close()
        conn.close()
        return jsonify({"error": "Comment not found"}), 404

    if int(comment["user_id"]) != user_id:
        cursor.close()
        conn.close()
        return jsonify({"error": "Unauthorized"}), 403

    cursor.execute("DELETE FROM votes WHERE comment_id = %s", (comment_id,))
    cursor.execute("DELETE FROM comments WHERE id = %s", (comment_id,))

    if comment["is_accepted"]:
        cursor.execute("""
            UPDATE posts
            SET is_resolved = FALSE
            WHERE id = %s
        """, (comment["post_id"],))

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"message": "Comment deleted successfully"})



