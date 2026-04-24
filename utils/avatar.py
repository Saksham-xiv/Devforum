from pathlib import Path
from werkzeug.utils import secure_filename


ALLOWED_AVATAR_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def get_avatar_directory(app):
    avatar_dir = Path(app.root_path) / app.config["AVATAR_UPLOAD_FOLDER"]
    avatar_dir.mkdir(parents=True, exist_ok=True)
    return avatar_dir


def find_avatar_filename(app, user_id):
    avatar_dir = get_avatar_directory(app)
    for file_path in avatar_dir.glob(f"user_{user_id}.*"):
        if file_path.suffix.lower() in ALLOWED_AVATAR_EXTENSIONS:
            return file_path.name
    return None


def save_avatar(app, user_id, uploaded_file):
    original_name = secure_filename(uploaded_file.filename or "")
    extension = Path(original_name).suffix.lower()

    if extension not in ALLOWED_AVATAR_EXTENSIONS:
        raise ValueError("Unsupported file type")

    avatar_dir = get_avatar_directory(app)

    for existing_file in avatar_dir.glob(f"user_{user_id}.*"):
        existing_file.unlink(missing_ok=True)

    filename = f"user_{user_id}{extension}"
    uploaded_file.save(avatar_dir / filename)
    return filename
