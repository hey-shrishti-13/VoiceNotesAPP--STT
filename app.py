import os
import uuid
import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, url_for
from utils.save_note import save_txt_docx
from sqlalchemy import create_engine, Column, Integer, String, DateTime, MetaData, Table, Text
from sqlalchemy.orm import sessionmaker

USE_WHISPER = True

if USE_WHISPER:
    import whisper

app = Flask(__name__)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
AUDIO_DIR = os.path.join(OUTPUT_DIR, "audio")
NOTES_DIR = os.path.join(OUTPUT_DIR, "notes")
os.makedirs(AUDIO_DIR, exist_ok=True)
os.makedirs(NOTES_DIR, exist_ok=True)

DB_PATH = os.path.join(BASE_DIR, "notes.db")
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False, future=True)

def check_and_create_schema():
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='notes'")
    table_exists = cursor.fetchone() is not None
    
    if table_exists:
        cursor.execute("PRAGMA table_info(notes)")
        columns = [column[1] for column in cursor.fetchall()]
        has_text_columns = 'orig_text' in columns and 'en_text' in columns
        has_category_column = 'category' in columns
    else:
        has_text_columns = False
        has_category_column = False
    
    conn.close()
    return table_exists, has_text_columns, has_category_column

table_exists, has_text_columns, has_category_column = check_and_create_schema()

metadata = MetaData()
if has_text_columns or not table_exists:
    if has_category_column or not table_exists:
        notes_table = Table(
            "notes", metadata,
            Column("id", Integer, primary_key=True),
            Column("filename", String, nullable=False),
            Column("language", String),
            Column("created_at", DateTime),
            Column("transcription_file", String),
            Column("docx_file", String),
            Column("audio_file", String),
            Column("orig_text", Text),
            Column("en_text", Text),
            Column("category", String, default="Others")
        )
    else:
        notes_table = Table(
            "notes", metadata,
            Column("id", Integer, primary_key=True),
            Column("filename", String, nullable=False),
            Column("language", String),
            Column("created_at", DateTime),
            Column("transcription_file", String),
            Column("docx_file", String),
            Column("audio_file", String),
            Column("orig_text", Text),
            Column("en_text", Text)
        )
else:
    notes_table = Table(
        "notes", metadata,
        Column("id", Integer, primary_key=True),
        Column("filename", String, nullable=False),
        Column("language", String),
        Column("created_at", DateTime),
        Column("transcription_file", String),
        Column("docx_file", String),
        Column("audio_file", String)
    )

metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()

_whisper_model = None
def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        _whisper_model = whisper.load_model("small")
    return _whisper_model

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/notes")
def list_notes():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    
    with engine.connect() as conn:
        try:
            query_conditions = []
            if q:
                # Search in filename, orig_text, and en_text
                if has_text_columns or not table_exists:
                    from sqlalchemy import or_
                    query_conditions.append(or_(
                        notes_table.c.filename.contains(q),
                        notes_table.c.orig_text.contains(q),
                        notes_table.c.en_text.contains(q)
                    ))
                else:
                    query_conditions.append(notes_table.c.filename.contains(q))
            
            if category:
                query_conditions.append(notes_table.c.category == category)
            
            if query_conditions:
                from sqlalchemy import and_
                stmt = notes_table.select().where(and_(*query_conditions)).order_by(notes_table.c.created_at.desc())
            else:
                stmt = notes_table.select().order_by(notes_table.c.created_at.desc())
            
            res = conn.execute(stmt).fetchall()
        except Exception as e:
            # Fallback for older schema
            from sqlalchemy import text
            query_parts = []
            params = {}
            
            if q:
                query_parts.append("filename LIKE :q")
                params["q"] = f"%{q}%"
            if category:
                query_parts.append("category = :category")
                params["category"] = category
            
            where_clause = " AND ".join(query_parts) if query_parts else "1=1"
            query_str = f"SELECT id, filename, language, created_at, transcription_file, docx_file, audio_file, NULL as orig_text, NULL as en_text, 'Others' as category FROM notes WHERE {where_clause} ORDER BY created_at DESC"
            res = conn.execute(text(query_str), params).fetchall()
    
    return render_template("list_notes.html", notes=res, query=q, selected_category=category)

@app.route("/upload_audio", methods=["POST"])
def upload_audio():
    """
    Accepts recorded audio blob (webm/wav) as file 'audio_data', saves temp file,
    runs transcription (original + english translation only for Hindi), and returns JSON.
    """
    f = request.files.get("audio_data")
    if not f:
        return jsonify({"error": "no audio_data uploaded"}), 400

    temp_filename = f"{datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}.webm"
    temp_audio_path = os.path.join(AUDIO_DIR, temp_filename)
    f.save(temp_audio_path)

    if USE_WHISPER:
        model = get_whisper_model()
        res_orig = model.transcribe(temp_audio_path, task="transcribe", language=None)
        orig_text = res_orig.get("text", "").strip()
        detected_lang = res_orig.get("language", "unknown")
        
        lang_mapping = {
            "hi": "hindi",
            "en": "english",
            "hindi": "hindi",
            "english": "english"
        }
        
        lang = lang_mapping.get(detected_lang.lower(), "unknown")
        
        if lang == "unknown":
            os.remove(temp_audio_path)
            return jsonify({
                "error": f"Language '{detected_lang}' not supported. Please speak in Hindi or English only."
            }), 400
        
        # Only generate English translation for Hindi audio
        if lang == "hindi":
            res_trans = model.transcribe(temp_audio_path, task="translate")
            en_text = res_trans.get("text", "").strip()
        else:
            # For English audio, don't generate translation
            en_text = ""
    else:
        orig_text = ""
        en_text = ""
        lang = "unknown"

    return jsonify({
        "orig_text": orig_text,
        "en_text": en_text,
        "language": lang,
        "temp_filename": temp_filename
    })

@app.route("/save_note", methods=["POST"])
def save_note():
    """
    Save the note with custom filename and category after user provides details
    """
    data = request.json
    temp_filename = data.get("temp_filename")
    custom_name = data.get("custom_name", "").strip()
    category = data.get("category", "Others")
    orig_text = data.get("orig_text", "")
    en_text = data.get("en_text", "")
    language = data.get("language", "unknown")
    
    if not temp_filename or not custom_name:
        return jsonify({"error": "Missing required data"}), 400
    
    import re
    clean_name = re.sub(r'[^\w\s-]', '', custom_name).strip()
    clean_name = re.sub(r'[-\s]+', '-', clean_name)
    
    temp_path = os.path.join(AUDIO_DIR, temp_filename)
    if not os.path.exists(temp_path):
        return jsonify({"error": "Temporary audio file not found"}), 400
    
    timestamp = datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')
    audio_filename = f"{timestamp}_{clean_name}.webm"
    txt_filename = f"{timestamp}_{clean_name}.txt"
    docx_filename = f"{timestamp}_{clean_name}.docx"
    
    final_audio_path = os.path.join(AUDIO_DIR, audio_filename)
    os.rename(temp_path, final_audio_path)
    
    txt_path = os.path.join(NOTES_DIR, txt_filename)
    docx_path = os.path.join(NOTES_DIR, docx_filename)
    save_txt_docx(txt_path, docx_path, orig_text, en_text, language=language)

    with engine.connect() as conn:
        if has_text_columns or not table_exists:
            if has_category_column or not table_exists:
                conn.execute(notes_table.insert().values(
                    filename=clean_name,
                    language=language,
                    created_at=datetime.datetime.utcnow(),
                    transcription_file=txt_filename,
                    docx_file=docx_filename,
                    audio_file=audio_filename,
                    orig_text=orig_text,
                    en_text=en_text,
                    category=category
                ))
            else:
                conn.execute(notes_table.insert().values(
                    filename=clean_name,
                    language=language,
                    created_at=datetime.datetime.utcnow(),
                    transcription_file=txt_filename,
                    docx_file=docx_filename,
                    audio_file=audio_filename,
                    orig_text=orig_text,
                    en_text=en_text
                ))
        else:
            conn.execute(notes_table.insert().values(
                filename=clean_name,
                language=language,
                created_at=datetime.datetime.utcnow(),
                transcription_file=txt_filename,
                docx_file=docx_filename,
                audio_file=audio_filename
            ))
        conn.commit()

    return jsonify({
        "success": True,
        "filename": clean_name,
        "category": category,
        "txt_file": url_for("download_note", filename=txt_filename),
        "docx_file": url_for("download_note", filename=docx_filename),
        "audio_file": url_for("get_audio", filename=audio_filename)
    })

@app.route('/delete_note', methods=['DELETE'])
def delete_note():
    try:
        txt_file = request.args.get('txt')
        docx_file = request.args.get('docx')
        audio_file = request.args.get('audio')

        deleted_files = []

        if txt_file:
            txt_path = os.path.join('outputs/notes', txt_file)
            if os.path.exists(txt_path):
                os.remove(txt_path)
                deleted_files.append(txt_file)

        if docx_file:
            docx_path = os.path.join('outputs/notes', docx_file)
            if os.path.exists(docx_path):
                os.remove(docx_path)
                deleted_files.append(docx_file)

        if audio_file:
            audio_path = os.path.join('outputs/audio', audio_file)
            if os.path.exists(audio_path):
                os.remove(audio_path)
                deleted_files.append(audio_file)

        if audio_file:  
            with engine.connect() as conn:
                stmt = notes_table.delete().where(notes_table.c.audio_file == audio_file)
                conn.execute(stmt)
                conn.commit()

        return jsonify({"success": True, "deleted": deleted_files})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/rename_note', methods=['PUT'])
def rename_note():
    try:
        txt_file = request.args.get('txt')
        docx_file = request.args.get('docx')
        audio_file = request.args.get('audio')
        new_name = request.args.get('new_name')

        if not new_name:
            return jsonify({"success": False, "error": "New name not provided"}), 400

        import re
        clean_name = re.sub(r'[^\w\s-]', '', new_name).strip()
        clean_name = re.sub(r'[-\s]+', '-', clean_name)

        renamed_files = {}

        if txt_file:
            old_path = os.path.join('outputs/notes', txt_file)
            timestamp = txt_file.split('_')[0] if '_' in txt_file else datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')
            new_txt = f"{timestamp}_{clean_name}.txt"
            new_path = os.path.join('outputs/notes', new_txt)
            if os.path.exists(old_path):
                os.rename(old_path, new_path)
                renamed_files['txt'] = new_txt

        if docx_file:
            old_path = os.path.join('outputs/notes', docx_file)
            timestamp = docx_file.split('_')[0] if '_' in docx_file else datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')
            new_docx = f"{timestamp}_{clean_name}.docx"
            new_path = os.path.join('outputs/notes', new_docx)
            if os.path.exists(old_path):
                os.rename(old_path, new_path)
                renamed_files['docx'] = new_docx

        if audio_file:
            old_path = os.path.join('outputs/audio', audio_file)
            ext = os.path.splitext(audio_file)[1]
            timestamp = audio_file.split('_')[0] if '_' in audio_file else datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')
            new_audio = f"{timestamp}_{clean_name}{ext}"
            new_path = os.path.join('outputs/audio', new_audio)
            if os.path.exists(old_path):
                os.rename(old_path, new_path)
                renamed_files['audio'] = new_audio

        if audio_file:
            with engine.connect() as conn:
                stmt = notes_table.update().where(notes_table.c.audio_file == audio_file).values(
                    filename=clean_name,
                    transcription_file=renamed_files.get('txt'),
                    docx_file=renamed_files.get('docx'),
                    audio_file=renamed_files.get('audio')
                )
                conn.execute(stmt)
                conn.commit()

        return jsonify({"success": True, "renamed": renamed_files})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/outputs/notes/<path:filename>")
def download_note(filename):
    return send_from_directory(NOTES_DIR, filename, as_attachment=True)

@app.route("/outputs/audio/<path:filename>")
def get_audio(filename):
    """Route to serve audio files for playback"""
    return send_from_directory(AUDIO_DIR, filename)

@app.route("/download_audio/<path:filename>")
def download_audio(filename):
    """Route to download audio files"""
    return send_from_directory(AUDIO_DIR, filename, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)