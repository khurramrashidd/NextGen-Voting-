import os
from werkzeug.utils import secure_filename
from datetime import datetime
from config import Config

# Optional face_recognition use
try:
    import face_recognition
    HAS_FR = True
except Exception:
    HAS_FR = False

ALLOWED_EXT = {'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT

def save_face_image(file_storage, voter_id):
    if not allowed_file(file_storage.filename):
        raise ValueError('File type not allowed')
    filename = secure_filename(f"{voter_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.jpg")
    path = os.path.join(Config.UPLOAD_FOLDER, filename)
    file_storage.save(path)
    return path

def encode_face_from_file(path):
    """
    Return face encoding using face_recognition if available.
    Otherwise return None (caller may fallback to naive matching).
    """
    if not HAS_FR:
        return None
    image = face_recognition.load_image_file(path)
    encs = face_recognition.face_encodings(image)
    if len(encs) == 0:
        return None
    return encs[0]

def compare_faces(known_encoding, unknown_encoding, tolerance=0.6):
    if not HAS_FR:
        return False
    return face_recognition.compare_faces([known_encoding], unknown_encoding, tolerance=tolerance)[0]
