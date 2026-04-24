from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from pathlib import Path
from config import Config
from db.postgres import get_connection

jwt = JWTManager()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    Path(app.root_path, app.config["AVATAR_UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    # Enable CORS
    CORS(app, supports_credentials=True)

    # Initialize JWT
    jwt.init_app(app)

    # -----------------------------
    # Database Connection Function
    # -----------------------------
    def get_db_connection():
        return get_connection(app)

    # Attach DB function to app
    app.get_db_connection = get_db_connection

    # -----------------------------
    # Register Blueprints
    # -----------------------------
    from routes.auth import auth_bp
    from routes.posts import posts_bp
    from routes.comments import comments_bp
    from routes.users import users_bp
    from routes.admin import admin_bp
    from routes.profile import profile_bp
    from routes.problems import problems_bp
    from routes.communities import communities_bp
    from routes.notifications import notifications_bp



    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(posts_bp, url_prefix="/api/posts", strict_slashes=False)
    app.register_blueprint(comments_bp, url_prefix="/api/comments")
    app.register_blueprint(users_bp, url_prefix="/api/users")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(profile_bp, url_prefix="/api/profile")
    app.register_blueprint(problems_bp, url_prefix="/api/problems")
    app.register_blueprint(communities_bp, url_prefix="/api/communities")
    app.register_blueprint(notifications_bp, url_prefix="/api/notifications")

    # -----------------------------
    # Health Check Route
    # -----------------------------
    @app.route("/")
    def home():
        return {"message": "DevForum AI 2.0 Backend Running"}

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
