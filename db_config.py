# projekt_gpx_viewer/db_config.py
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, func, event, ForeignKey, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy.engine import Engine
from pathlib import Path
import json
from datetime import datetime, timedelta # timedelta hinzugefügt
from typing import List, Optional, Tuple, Any, Dict
import traceback
from passlib.context import CryptContext
import secrets # Für sichere Zufallscodes

BASE_DIR = Path(__file__).resolve().parent
GPX_UPLOAD_DIR = BASE_DIR / "gpx_uploads"
GPX_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_URL = f"sqlite:///{BASE_DIR / 'tracks_users_sqlalchemy.db'}"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
class UserDB(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False) # E-Mail wird nun Pflichtfeld für 2FA
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=func.now())
    
    is_2fa_enabled = Column(Boolean, default=False, nullable=False)
    email_2fa_code = Column(String, nullable=True) 
    email_2fa_code_expires_at = Column(DateTime, nullable=True)
class TrackDB(Base):
    __tablename__ = "tracks"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, index=True, nullable=False)
    original_filename = Column(String, nullable=True)
    stored_filename = Column(String, nullable=False, unique=True)
    distance_km = Column(Float, nullable=True)
    upload_date = Column(DateTime, default=func.now())
    track_date = Column(DateTime, nullable=True)
    labels = Column(Text, default="[]")
    gpx_parsed_total_ascent = Column(Float, nullable=True)
    gpx_parsed_total_descent = Column(Float, nullable=True)

def create_db_tables():
    Base.metadata.create_all(bind=engine)
    print("SQLAlchemy Datenbanktabellen (Users, Tracks) überprüft/erstellt.")

create_db_tables()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def generate_email_2fa_code(length: int = 6) -> str:
    return "".join(secrets.choice("0123456789") for _ in range(length))

def send_2fa_email(recipient_email: str, code: str):
    print(f"SIMULATING EMAIL to {recipient_email}: Your 2FA code is {code}")
    #Mailkonfig folgt
    return True 

def get_user_by_username(db: Session, username: str) -> Optional[UserDB]:
    return db.query(UserDB).filter(UserDB.username == username).first()

def get_user_by_id(db: Session, user_id: int) -> Optional[UserDB]:
    return db.query(UserDB).filter(UserDB.id == user_id).first()

def create_user(db: Session, username: str, password: str, email: str) -> UserDB: 
    if not email: 
        raise ValueError("Email is required for user creation.")
    hashed_password = get_password_hash(password)
    db_user = UserDB(username=username, hashed_password=hashed_password, email=email)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def set_email_2fa_code_for_user(db: Session, user_id: int, code_lifetime_minutes: int = 10) -> Optional[str]:
    user = get_user_by_id(db, user_id)
    if user and user.email: 
        code = generate_email_2fa_code()
        user.email_2fa_code = get_password_hash(code) 
        user.email_2fa_code_expires_at = datetime.utcnow() + timedelta(minutes=code_lifetime_minutes)
        db.commit()
        return code 
    return None

def verify_email_2fa_code(db: Session, user_id: int, code_attempt: str) -> bool:
    user = get_user_by_id(db, user_id)
    if user and user.email_2fa_code and user.email_2fa_code_expires_at:
        if datetime.utcnow() > user.email_2fa_code_expires_at:
            user.email_2fa_code = None
            user.email_2fa_code_expires_at = None
            db.commit()
            return False
        
        is_valid = verify_password(code_attempt, user.email_2fa_code)
        
        if is_valid:
            user.email_2fa_code = None
            user.email_2fa_code_expires_at = None
            db.commit()
            return True
    return False

def enable_email_2fa(db: Session, user_id: int) -> bool:
    user = get_user_by_id(db, user_id)
    if user and user.email: 
        user.is_2fa_enabled = True
        user.email_2fa_code = None
        user.email_2fa_code_expires_at = None
        db.commit()
        return True
    return False

def disable_email_2fa(db: Session, user_id: int) -> bool:
    user = get_user_by_id(db, user_id)
    if user:
        user.is_2fa_enabled = False
        user.email_2fa_code = None
        user.email_2fa_code_expires_at = None
        db.commit()
        return True
    return False

def add_track(
    db: Session,
    user_id: int, 
    parsed_gpx_data: Dict[str, Any],
    gpx_file_content_bytes: bytes
) -> Optional[int]:
    original_filename = parsed_gpx_data.get("original_filename", "unknown.gpx")
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
    safe_original_filename = "".join(c if c.isalnum() or c in ('.', '_', '-') else '_' for c in original_filename)
    stored_filename = f"{timestamp}_{safe_original_filename}"
    filepath_on_server = GPX_UPLOAD_DIR / stored_filename
    try:
        with open(filepath_on_server, "wb") as f:
            f.write(gpx_file_content_bytes)
        db_track = TrackDB(
            user_id=user_id, 
            name=parsed_gpx_data.get("track_name", "Unbenannter Track"),
            original_filename=original_filename,
            stored_filename=stored_filename,
            distance_km=parsed_gpx_data.get("distance_km"),
            track_date=parsed_gpx_data.get("track_date"),
            labels=json.dumps(parsed_gpx_data.get("labels_list", [])),
            gpx_parsed_total_ascent=parsed_gpx_data.get("total_ascent"),
            gpx_parsed_total_descent=parsed_gpx_data.get("total_descent")
        )
        db.add(db_track)
        db.commit()
        db.refresh(db_track)
        print(f"Track '{db_track.name}' (ID: {db_track.id}) für User ID {user_id} in DB gespeichert. Datei: {stored_filename}")
        return db_track.id
    except Exception as e:
        db.rollback()
        print(f"Fehler beim Hinzufügen des Tracks zur DB für User ID {user_id}: {e}")
        traceback.print_exc()
        if filepath_on_server.exists():
            try:
                filepath_on_server.unlink()
            except Exception as e_file:
                print(f"Fehler beim Aufräumen der Datei {filepath_on_server}: {e_file}")
        return None

def get_track_details(db: Session, user_id: int, track_id: int) -> Optional[TrackDB]:
    return db.query(TrackDB).filter(TrackDB.id == track_id, TrackDB.user_id == user_id).first()

def get_filtered_tracks(
    db: Session, user_id: int, start_date_str: Optional[str] = None,
    end_date_str: Optional[str] = None, label_filter_list: Optional[List[str]] = None
) -> List[TrackDB]:
    query = db.query(TrackDB).filter(TrackDB.user_id == user_id)
    try:
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            query = query.filter(TrackDB.track_date >= start_date)
        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            query = query.filter(TrackDB.track_date <= end_date)
        if label_filter_list:
            for label in label_filter_list:
                query = query.filter(TrackDB.labels.like(f'%"{label}"%'))
        return query.order_by(TrackDB.track_date.desc().nullslast(), TrackDB.id.desc()).all()
    except ValueError as ve:
        print(f"Datumsformatfehler im Filter für User ID {user_id}: {ve}")
        return db.query(TrackDB).filter(TrackDB.user_id == user_id).order_by(TrackDB.track_date.desc().nullslast(), TrackDB.id.desc()).all()
    except Exception as e:
        print(f"Fehler beim Filtern von Tracks für User ID {user_id}: {e}")
        traceback.print_exc()
        return []

def update_track_details(db: Session, user_id: int, track_id: int, new_name: str, new_labels_list: List[str]) -> bool:
    track = db.query(TrackDB).filter(TrackDB.id == track_id, TrackDB.user_id == user_id).first()
    if track:
        track.name = new_name.strip() if new_name.strip() else "Unbenannter Track"
        track.labels = json.dumps(sorted(list(set(new_labels_list))))
        try:
            db.commit(); return True
        except Exception as e:
            db.rollback()
            print(f"Fehler beim Aktualisieren von Track ID {track_id} für User ID {user_id}: {e}")
            traceback.print_exc()
            return False
    return False

def delete_track_by_id_with_file(db: Session, user_id: int, track_id: int) -> Optional[str]:
    track = db.query(TrackDB).filter(TrackDB.id == track_id, TrackDB.user_id == user_id).first()
    if track:
        track_name_for_notification = track.name
        filepath_to_delete = GPX_UPLOAD_DIR / track.stored_filename
        try:
            db.delete(track); db.commit()
            if filepath_to_delete.exists(): filepath_to_delete.unlink()
            return track_name_for_notification
        except Exception as e:
            db.rollback()
            print(f"Fehler beim Löschen von Track ID {track_id} für User ID {user_id}: {e}")
            traceback.print_exc()
            return None
    return None

def delete_multiple_tracks_with_files(db: Session, user_id: int, track_ids: List[int]) -> Tuple[int, List[str]]:
    if not track_ids: return 0, []
    tracks_to_delete = db.query(TrackDB).filter(TrackDB.id.in_(track_ids), TrackDB.user_id == user_id).all()
    deleted_count = 0; errors = []
    files_to_delete_paths = []
    for track in tracks_to_delete:
        files_to_delete_paths.append(GPX_UPLOAD_DIR / track.stored_filename)
        try: db.delete(track)
        except Exception as e_del_obj:
            db.rollback()
            errors.append(f"Fehler beim Vorbereiten des Löschens für Track ID {track.id}: {e_del_obj}")
            return 0, errors + [f"DB-Vorbereitung fehlgeschlagen für User ID {user_id}, keine Tracks gelöscht."]
    try:
        db.commit(); deleted_count = len(tracks_to_delete)
        for f_path in files_to_delete_paths:
            if f_path.exists():
                try: f_path.unlink()
                except Exception as e_file_del: errors.append(f"Konnte Datei {f_path} nicht löschen: {e_file_del}")
        print(f"{deleted_count} Tracks für User ID {user_id} gelöscht.")
    except Exception as e_commit:
        db.rollback(); errors.append(f"Fehler beim finalen DB-Commit für User ID {user_id}: {e_commit}")
        traceback.print_exc()
        return 0, errors + [f"DB-Commit fehlgeschlagen, keine Tracks gelöscht."]
    return deleted_count, errors

def get_all_unique_labels(db: Session, user_id: int) -> List[str]:
    all_labels_json_strings = db.query(TrackDB.labels).filter(TrackDB.user_id == user_id).distinct().all()
    unique_labels_set = set()
    for (labels_json,) in all_labels_json_strings:
        if labels_json and labels_json.strip() and labels_json != "null":
            try:
                labels_list = json.loads(labels_json)
                for label in labels_list:
                    if label and label.strip(): unique_labels_set.add(label.strip())
            except json.JSONDecodeError:
                print(f"Warnung: Ungültiger JSON-String für Labels in DB (User ID {user_id}): {labels_json}")
    return sorted(list(unique_labels_set))

def get_gpx_filepath(db: Session, user_id: int, track_id: int) -> Optional[Path]:
    track = db.query(TrackDB).filter(TrackDB.id == track_id, TrackDB.user_id == user_id).first()
    if track and track.stored_filename:
        return GPX_UPLOAD_DIR / track.stored_filename
    return None