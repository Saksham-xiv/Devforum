from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from utils.gamification import sync_user_progress
from utils.notifications import create_notification

communities_bp = Blueprint("communities", __name__)


def _community_payload(cursor, row, user_id):
    community_id = row["id"]

    cursor.execute(
        """
        SELECT COUNT(*) AS member_count
        FROM community_members
        WHERE community_id = %s
        """,
        (community_id,),
    )
    member_row = cursor.fetchone()
    members = int(member_row["member_count"] or 0)

    cursor.execute(
        """
        SELECT COUNT(*) AS joined
        FROM community_members
        WHERE community_id = %s AND user_id = %s
        """,
        (community_id, user_id),
    )
    joined_row = cursor.fetchone()
    joined = int(joined_row["joined"] or 0) > 0

    cursor.execute(
        """
        SELECT COUNT(*) AS discussions
        FROM posts
        WHERE community_id = %s
        """,
        (community_id,),
    )
    discussion_row = cursor.fetchone()
    discussions = int(discussion_row["discussions"] or 0)

    cursor.execute(
        """
        SELECT posts.title, posts.content, users.username, posts.created_at
        FROM posts
        JOIN users ON users.id = posts.user_id
        WHERE posts.community_id = %s
        ORDER BY posts.created_at DESC
        LIMIT 3
        """,
        (community_id,),
    )
    posts = [
        {
            "title": post["title"],
            "author": post["username"],
            "excerpt": (post["content"] or "")[:140],
            "time": post["created_at"].strftime("%Y-%m-%d %H:%M"),
        }
        for post in cursor.fetchall()
    ]

    return {
        "id": community_id,
        "name": row["name"],
        "description": row["description"],
        "topic": row["topic"],
        "members": members,
        "joined": joined,
        "discussions": discussions,
        "posts": posts,
    }


@communities_bp.route("/", methods=["GET"])
@jwt_required()
def list_communities():
    user_id = int(get_jwt_identity())
    conn = current_app.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, name, description, topic
        FROM communities
        ORDER BY created_at DESC, id DESC
        """
    )
    communities = [_community_payload(cursor, row, user_id) for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return jsonify(communities)


@communities_bp.route("/", methods=["POST"])
@jwt_required()
def create_community():
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    topic = (data.get("topic") or "").strip()
    description = (data.get("description") or "").strip()

    if not name or not topic or not description:
        return jsonify({"error": "Name, topic, and description are required"}), 400

    conn = current_app.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO communities (name, description, topic, creator_id)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (name, description, topic, user_id),
    )
    community_id = cursor.fetchone()["id"]

    cursor.execute(
        """
        INSERT INTO community_members (community_id, user_id, role_name)
        VALUES (%s, %s, 'owner')
        ON CONFLICT (community_id, user_id) DO NOTHING
        """,
        (community_id, user_id),
    )

    cursor.execute(
        """
        INSERT INTO posts (user_id, title, content, community_id, post_type)
        VALUES (%s, %s, %s, %s, 'community')
        """,
        (
            user_id,
            f"Welcome to {name}",
            "Community created. Start the first discussion and invite collaborators.",
            community_id,
        ),
    )

    sync_user_progress(cursor, user_id)
    create_notification(
        cursor,
        user_id,
        "community",
        "Community created",
        f"{name} is ready for developers to join.",
        related_community_id=community_id,
    )

    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "Community created", "community_id": community_id}), 201


@communities_bp.route("/<int:community_id>/join", methods=["POST"])
@jwt_required()
def join_community(community_id):
    user_id = int(get_jwt_identity())
    conn = current_app.get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM communities WHERE id = %s", (community_id,))
    community = cursor.fetchone()
    if not community:
        cursor.close()
        conn.close()
        return jsonify({"error": "Community not found"}), 404

    cursor.execute(
        """
        INSERT INTO community_members (community_id, user_id, role_name)
        VALUES (%s, %s, 'member')
        ON CONFLICT (community_id, user_id) DO NOTHING
        """,
        (community_id, user_id),
    )

    sync_user_progress(cursor, user_id)
    create_notification(
        cursor,
        user_id,
        "community",
        "Joined community",
        f"You are now following {community['name']}.",
        related_community_id=community_id,
    )

    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "Joined community"})


@communities_bp.route("/<int:community_id>/join", methods=["DELETE"])
@jwt_required()
def leave_community(community_id):
    user_id = int(get_jwt_identity())
    conn = current_app.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        DELETE FROM community_members
        WHERE community_id = %s AND user_id = %s AND role_name <> 'owner'
        """,
        (community_id, user_id),
    )
    sync_user_progress(cursor, user_id)
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "Left community"})

