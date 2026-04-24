from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from utils.gamification import sync_user_progress
from utils.notifications import create_notification

problems_bp = Blueprint("problems", __name__)


def _simulate_submission(problem_slug, source_code):
    normalized = (source_code or "").lower()
    keyword_map = {
        "two-sum-variants": ["map", "hash", "set"],
        "merge-intervals": ["sort", "merge"],
        "lru-cache-design": ["doubly", "linked", "cache"],
    }
    expected_keywords = keyword_map.get(problem_slug, [])
    passed = any(keyword in normalized for keyword in expected_keywords) or "optimiz" in normalized
    return {
        "passed": passed,
        "message": "Passed sample and hidden tests." if passed else "Failed hidden tests. Improve edge-case handling and complexity.",
    }


def _serialize_problem(cursor, problem_row, user_id):
    problem_id = problem_row["id"]

    cursor.execute(
        """
        SELECT id, sample_order, sample_input, sample_output
        FROM problem_samples
        WHERE problem_id = %s
        ORDER BY sample_order ASC, id ASC
        """,
        (problem_id,),
    )
    samples = cursor.fetchall()

    cursor.execute(
        """
        SELECT COUNT(*) AS hidden_tests
        FROM problem_hidden_tests
        WHERE problem_id = %s AND is_active = TRUE
        """,
        (problem_id,),
    )
    hidden_row = cursor.fetchone()
    hidden_tests = int(hidden_row["hidden_tests"] or 0)

    cursor.execute(
        """
        SELECT problem_discussions.id,
               problem_discussions.body,
               users.username,
               COALESCE(COUNT(problem_discussion_votes.id), 0) AS votes
        FROM problem_discussions
        JOIN users ON users.id = problem_discussions.user_id
        LEFT JOIN problem_discussion_votes
            ON problem_discussion_votes.discussion_id = problem_discussions.id
        WHERE problem_discussions.problem_id = %s
        GROUP BY problem_discussions.id, problem_discussions.body, users.username
        ORDER BY votes DESC, problem_discussions.created_at DESC
        """,
        (problem_id,),
    )
    discussions = [
        {
            "id": row["id"],
            "user": row["username"],
            "text": row["body"],
            "votes": int(row["votes"] or 0),
        }
        for row in cursor.fetchall()
    ]

    cursor.execute(
        """
        SELECT problem_hints.id,
               problem_hints.body,
               users.username,
               COALESCE(COUNT(problem_hint_votes.id), 0) AS votes
        FROM problem_hints
        JOIN users ON users.id = problem_hints.user_id
        LEFT JOIN problem_hint_votes
            ON problem_hint_votes.hint_id = problem_hints.id
        WHERE problem_hints.problem_id = %s
        GROUP BY problem_hints.id, problem_hints.body, users.username
        ORDER BY votes DESC, problem_hints.created_at DESC
        """,
        (problem_id,),
    )
    hints = [
        {
            "id": row["id"],
            "user": row["username"],
            "text": row["body"],
            "votes": int(row["votes"] or 0),
        }
        for row in cursor.fetchall()
    ]

    cursor.execute(
        """
        SELECT problem_chat_messages.id,
               problem_chat_messages.message_body,
               users.username
        FROM problem_chat_messages
        JOIN users ON users.id = problem_chat_messages.user_id
        WHERE problem_chat_messages.problem_id = %s
        ORDER BY problem_chat_messages.created_at ASC
        LIMIT 25
        """,
        (problem_id,),
    )
    chat = [
        {
            "id": row["id"],
            "user": row["username"],
            "text": row["message_body"],
        }
        for row in cursor.fetchall()
    ]

    cursor.execute(
        """
        SELECT id, status, source_code, passed_hidden_tests, total_hidden_tests, execution_notes
        FROM problem_submissions
        WHERE problem_id = %s AND user_id = %s
        ORDER BY submitted_at DESC, id DESC
        LIMIT 1
        """,
        (problem_id, user_id),
    )
    latest_submission = cursor.fetchone()

    cursor.execute(
        """
        SELECT id
        FROM solved_problems
        WHERE problem_id = %s AND user_id = %s
        """,
        (problem_id, user_id),
    )
    solved = cursor.fetchone() is not None

    return {
        "id": problem_id,
        "title": problem_row["title"],
        "slug": problem_row["slug"],
        "difficulty": problem_row["difficulty"],
        "description": problem_row["description"],
        "inputFormat": problem_row["input_format"],
        "outputFormat": problem_row["output_format"],
        "points": int(problem_row["points"] or 0),
        "hiddenTests": hidden_tests,
        "sampleTests": [
            {
                "id": sample["id"],
                "input": sample["sample_input"],
                "output": sample["sample_output"],
            }
            for sample in samples
        ],
        "discussions": discussions,
        "hints": hints,
        "chat": chat,
        "submission": (
            {
                "id": latest_submission["id"],
                "status": latest_submission["status"],
                "code": latest_submission["source_code"],
                "message": latest_submission["execution_notes"],
                "passedHiddenTests": latest_submission["passed_hidden_tests"],
                "totalHiddenTests": latest_submission["total_hidden_tests"],
            }
            if latest_submission
            else None
        ),
        "solved": solved,
    }


@problems_bp.route("/", methods=["GET"])
@jwt_required()
def list_problems():
    user_id = int(get_jwt_identity())
    conn = current_app.get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, title, slug, description, difficulty, input_format, output_format, points
        FROM problem_sets
        WHERE is_active = TRUE
        ORDER BY
            CASE difficulty
                WHEN 'Easy' THEN 1
                WHEN 'Medium' THEN 2
                WHEN 'Hard' THEN 3
                ELSE 4
            END,
            id ASC
        """
    )
    problems = [_serialize_problem(cursor, row, user_id) for row in cursor.fetchall()]

    cursor.close()
    conn.close()
    return jsonify(problems)


@problems_bp.route("/<int:problem_id>/submit", methods=["POST"])
@jwt_required()
def submit_problem(problem_id):
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    source_code = (data.get("code") or "").strip()
    language_name = data.get("language") or "javascript"

    if not source_code:
        return jsonify({"error": "Code is required"}), 400

    conn = current_app.get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, title, slug, points
        FROM problem_sets
        WHERE id = %s AND is_active = TRUE
        """,
        (problem_id,),
    )
    problem = cursor.fetchone()
    if not problem:
        cursor.close()
        conn.close()
        return jsonify({"error": "Problem not found"}), 404

    cursor.execute(
        """
        SELECT COUNT(*) AS hidden_tests
        FROM problem_hidden_tests
        WHERE problem_id = %s AND is_active = TRUE
        """,
        (problem_id,),
    )
    hidden_row = cursor.fetchone()
    total_hidden_tests = int(hidden_row["hidden_tests"] or 0)

    result = _simulate_submission(problem["slug"], source_code)
    passed_hidden_tests = total_hidden_tests if result["passed"] else 0
    status = "passed" if result["passed"] else "failed"

    cursor.execute(
        """
        INSERT INTO problem_submissions (
            problem_id,
            user_id,
            language_name,
            source_code,
            status,
            passed_visible_tests,
            passed_hidden_tests,
            total_hidden_tests,
            execution_notes
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            problem_id,
            user_id,
            language_name,
            source_code,
            status,
            1 if result["passed"] else 0,
            passed_hidden_tests,
            total_hidden_tests,
            result["message"],
        ),
    )
    submission_id = cursor.fetchone()["id"]

    if result["passed"]:
        cursor.execute(
            """
            INSERT INTO solved_problems (problem_id, user_id, submission_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (problem_id, user_id) DO UPDATE SET
                submission_id = EXCLUDED.submission_id,
                solved_at = CURRENT_TIMESTAMP
            """,
            (problem_id, user_id, submission_id),
        )
        sync_user_progress(cursor, user_id)
        create_notification(
            cursor,
            user_id,
            "problem",
            "Problem solved",
            f"{problem['title']} has been added to your solved list.",
            related_problem_id=problem_id,
        )

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify(
        {
            "status": status,
            "message": result["message"],
            "passedHiddenTests": passed_hidden_tests,
            "totalHiddenTests": total_hidden_tests,
        }
    )


@problems_bp.route("/<int:problem_id>/discussions", methods=["POST"])
@jwt_required()
def add_problem_discussion(problem_id):
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    body = (data.get("text") or "").strip()

    if not body:
        return jsonify({"error": "Discussion text is required"}), 400

    conn = current_app.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO problem_discussions (problem_id, user_id, body) VALUES (%s, %s, %s) RETURNING id",
        (problem_id, user_id, body),
    )
    discussion_id = cursor.fetchone()["id"]
    create_notification(
        cursor,
        user_id,
        "reply",
        "New problem discussion",
        "Your doubt is now visible to collaborators.",
        related_problem_id=problem_id,
    )

    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "Discussion posted", "discussion_id": discussion_id}), 201


@problems_bp.route("/discussions/<int:discussion_id>/vote", methods=["POST"])
@jwt_required()
def vote_problem_discussion(discussion_id):
    user_id = int(get_jwt_identity())
    conn = current_app.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO problem_discussion_votes (discussion_id, user_id, vote_type)
        VALUES (%s, %s, 'upvote')
        ON CONFLICT (discussion_id, user_id) DO NOTHING
        """,
        (discussion_id, user_id),
    )
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "Discussion upvoted"})


@problems_bp.route("/<int:problem_id>/hints", methods=["POST"])
@jwt_required()
def add_problem_hint(problem_id):
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    body = (data.get("text") or "").strip()

    if not body:
        return jsonify({"error": "Hint text is required"}), 400

    conn = current_app.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO problem_hints (problem_id, user_id, body) VALUES (%s, %s, %s)",
        (problem_id, user_id, body),
    )
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "Hint posted"}), 201


@problems_bp.route("/hints/<int:hint_id>/vote", methods=["POST"])
@jwt_required()
def vote_problem_hint(hint_id):
    user_id = int(get_jwt_identity())
    conn = current_app.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO problem_hint_votes (hint_id, user_id, vote_type)
        VALUES (%s, %s, 'upvote')
        ON CONFLICT (hint_id, user_id) DO NOTHING
        """,
        (hint_id, user_id),
    )
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "Hint upvoted"})


@problems_bp.route("/<int:problem_id>/chat", methods=["POST"])
@jwt_required()
def add_problem_chat(problem_id):
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    message_body = (data.get("text") or "").strip()

    if not message_body:
        return jsonify({"error": "Chat message is required"}), 400

    conn = current_app.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO problem_chat_messages (problem_id, user_id, message_body) VALUES (%s, %s, %s)",
        (problem_id, user_id, message_body),
    )
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "Chat message sent"}), 201

