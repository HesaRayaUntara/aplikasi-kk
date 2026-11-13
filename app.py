import os
import re
import secrets
import uuid
from datetime import datetime

import mysql.connector
from flask import Flask, abort, flash, redirect, render_template, request, send_from_directory, session, url_for
from PIL import Image, UnidentifiedImageError
from werkzeug.utils import secure_filename

from database import get_db_connection
from ocr import ImageQualityError, process_kk_image

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)
app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "uploads")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png"}
IDENTITY_FIELDS = ("no_kk", "kepala_keluarga", "alamat", "rt", "rw", "desa_kelurahan", "kecamatan", "kabupaten_kota", "provinsi", "kode_pos", "tanggal_dikeluarkan")
MEMBER_FIELDS = ("nama_lengkap", "nik", "jenis_kelamin", "tempat_lahir", "tanggal_lahir", "agama", "pendidikan", "jenis_pekerjaan", "golongan_darah", "status_perkawinan", "tanggal_perkawinan", "status_hubungan", "kewarganegaraan", "no_paspor", "no_kitap", "nama_ayah", "nama_ibu")
MEMBER_LABELS = (("nama_lengkap", "Nama Lengkap"), ("nik", "NIK"), ("jenis_kelamin", "Jenis Kelamin"), ("tempat_lahir", "Tempat Lahir"), ("tanggal_lahir", "Tanggal Lahir"), ("agama", "Agama"), ("pendidikan", "Pendidikan"), ("jenis_pekerjaan", "Jenis Pekerjaan"), ("golongan_darah", "Golongan Darah"), ("status_perkawinan", "Status Perkawinan"), ("tanggal_perkawinan", "Tanggal Perkawinan"), ("status_hubungan", "Status Hubungan"), ("kewarganegaraan", "Kewarganegaraan"), ("no_paspor", "Nomor Paspor"), ("no_kitap", "Nomor KITAP"), ("nama_ayah", "Nama Ayah"), ("nama_ibu", "Nama Ibu"))
DATE_FIELDS = {"tanggal_dikeluarkan", "tanggal_lahir", "tanggal_perkawinan"}
TEXT_LIMITS = {"kepala_keluarga":100,"rt":5,"rw":5,"desa_kelurahan":100,"kecamatan":100,"kabupaten_kota":100,"provinsi":100,"kode_pos":10,"nama_lengkap":100,"nik":30,"jenis_kelamin":20,"tempat_lahir":100,"agama":30,"pendidikan":100,"jenis_pekerjaan":100,"golongan_darah":10,"status_perkawinan":50,"status_hubungan":50,"kewarganegaraan":10,"no_paspor":30,"no_kitap":30,"nama_ayah":100,"nama_ibu":100}
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


@app.context_processor
def inject_csrf_token():
    token = session.setdefault("_csrf_token", secrets.token_urlsafe(32))
    return {"csrf_token": token}


@app.before_request
def protect_post_requests():
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        expected = session.get("_csrf_token", "")
        supplied = request.form.get("_csrf_token", "")
        if not expected or not supplied or not secrets.compare_digest(expected, supplied):
            abort(400)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def parse_date(value, label):
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Format {label} tidak valid. Gunakan DD-MM-YYYY atau YYYY-MM-DD.")


def clean_text(value, field):
    value = (value or "").strip()
    limit = TEXT_LIMITS.get(field)
    if value and limit and len(value) > limit:
        raise ValueError(f"{field.replace('_', ' ').title()} maksimal {limit} karakter.")
    return value or None


def request_identity():
    return {field: request.form.get(f"identitas_kk[{field}]", "") for field in IDENTITY_FIELDS}


def request_members():
    rows = {}
    for key, value in request.form.items():
        match = re.fullmatch(r"anggota\[(\d+)\]\[([a-z_]+)\]", key)
        if match:
            rows.setdefault(int(match.group(1)), {})[match.group(2)] = value
    return [rows[index] for index in sorted(rows)]


def collect_form_data():
    identity = {}
    for field in IDENTITY_FIELDS:
        value = request.form.get(f"identitas_kk[{field}]", "").strip()
        if field == "no_kk":
            value = re.sub(r"\D", "", value)
            if len(value) != 16:
                raise ValueError("Nomor KK wajib terdiri dari 16 digit.")
            identity[field] = value
        elif field == "kepala_keluarga":
            identity[field] = clean_text(value, field)
            if not identity[field]:
                raise ValueError("Nama kepala keluarga wajib diisi.")
        elif field in DATE_FIELDS:
            identity[field] = parse_date(value, field.replace("_", " "))
        else:
            identity[field] = clean_text(value, field)

    indexed = {}
    for key, value in request.form.items():
        match = re.fullmatch(r"anggota\[(\d+)\]\[([a-z_]+)\]", key)
        if match:
            index, field = int(match.group(1)), match.group(2)
            if field in MEMBER_FIELDS or field == "id_anggota":
                indexed.setdefault(index, {})[field] = value.strip()
    members = []
    for index in sorted(indexed):
        submitted, member = indexed[index], {}
        for field in MEMBER_FIELDS:
            value = submitted.get(field, "")
            if field in DATE_FIELDS:
                member[field] = parse_date(value, field.replace("_", " "))
            elif field == "nik":
                digits = re.sub(r"\D", "", value)
                if value.strip() not in {"", "-", "—", "."} and len(digits) != 16:
                    raise ValueError(f"NIK anggota {index + 1} harus terdiri dari 16 digit.")
                member[field] = digits or None
            else:
                member[field] = clean_text(value, field)
        if not any(member.values()):
            continue
        if not member["nama_lengkap"]:
            raise ValueError(f"Nama anggota pada baris {index + 1} wajib diisi.")
        member["id_anggota"] = submitted.get("id_anggota", "") or None
        members.append(member)
    if not members:
        raise ValueError("Tambahkan setidaknya satu anggota keluarga.")
    return identity, members


def render_confirm(filename, identity=None, members=None, ocr_result=None, status=200):
    return render_template("konfirmasi.html", filename=filename, ocr_result=ocr_result or {},
        identitas_kk=identity or (ocr_result or {}).get("identity_data") or {field: "" for field in IDENTITY_FIELDS},
        members=members or [], member_fields=MEMBER_LABELS), status


def get_kk(kk_id):
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT * FROM tbl_identitasKK WHERE id_kk=%s", (kk_id,))
        kk = cur.fetchone()
        if not kk:
            abort(404)
        cur.execute("SELECT * FROM tbl_anggotaKeluargaKK WHERE id_kk=%s ORDER BY id_anggota", (kk_id,))
        kk["anggota"] = cur.fetchall()
        return kk
    finally:
        cur.close()
        conn.close()


def insert_members(cur, kk_id, members):
    columns = ", ".join(MEMBER_FIELDS)
    placeholders = ", ".join(["%s"] * len(MEMBER_FIELDS))
    query = f"INSERT INTO tbl_anggotaKeluargaKK (id_kk, {columns}) VALUES (%s, {placeholders})"
    for member in members:
        cur.execute(query, (kk_id, *(member[field] for field in MEMBER_FIELDS)))


@app.route("/")
def index():
    conn = cur = None
    error = None
    total_kk = total_anggota = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM tbl_identitasKK")
        total_kk = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM tbl_anggotaKeluargaKK")
        total_anggota = cur.fetchone()[0]
    except Exception:
        app.logger.exception("Gagal memuat ringkasan dashboard.")
        error = "Ringkasan belum dapat dimuat. Periksa koneksi aplikasi lalu coba lagi."
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()
    return render_template("index.html", summary_available=error is None,
        total_kk=total_kk, total_anggota=total_anggota, error_message=error)


@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "GET":
        return render_template("upload.html", uploaded=False)
    file = request.files.get("file_kk")
    if not file or not file.filename:
        flash("Silakan pilih gambar KK terlebih dahulu.", "error")
        return redirect(url_for("upload"))
    if not allowed_file(file.filename):
        flash("Format tidak didukung. Gunakan JPG, JPEG, atau PNG.", "error")
        return redirect(url_for("upload"))
    extension = secure_filename(file.filename).rsplit(".", 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{extension}"
    path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    try:
        image = Image.open(file.stream)
        image.verify()
        file.stream.seek(0)
        image = Image.open(file.stream)
        if image.width < 300 or image.height < 200:
            flash("Resolusi gambar minimal 300 × 200 piksel.", "error")
            return redirect(url_for("upload"))
        file.stream.seek(0)
        file.save(path)
        result = process_kk_image(path)
        return render_confirm(filename, identity=result.get("identity_data"), members=result.get("members", []), ocr_result=result)
    except ImageQualityError as error:
        if os.path.exists(path): os.remove(path)
        flash(f"{error} Silakan unggah gambar yang lebih jelas.", "error")
    except (UnidentifiedImageError, OSError, ValueError) as error:
        if os.path.exists(path): os.remove(path)
        app.logger.warning("File upload tidak valid: %s", error)
        flash("File tidak valid atau gambar tidak dapat dibaca.", "error")
    except Exception:
        if os.path.exists(path): os.remove(path)
        app.logger.exception("Gagal memproses upload/OCR.")
        flash("Terjadi kesalahan saat membaca gambar KK. Silakan coba lagi.", "error")
    return redirect(url_for("upload"))


@app.route("/kk/simpan", methods=["POST"])
def simpan_kk():
    filename = request.form.get("source_filename", "")
    try:
        identity, members = collect_form_data()
    except ValueError as error:
        flash(str(error), "error")
        return render_confirm(filename, request_identity(), request_members(), status=400)
    conn = cur = None
    try:
        conn = get_db_connection()
        conn.start_transaction()
        cur = conn.cursor()
        columns = ", ".join(IDENTITY_FIELDS)
        placeholders = ", ".join(["%s"] * len(IDENTITY_FIELDS))
        cur.execute(f"INSERT INTO tbl_identitasKK ({columns}) VALUES ({placeholders})",
            tuple(identity[field] for field in IDENTITY_FIELDS))
        kk_id = cur.lastrowid
        insert_members(cur, kk_id, members)
        conn.commit()
        flash("Data Kartu Keluarga berhasil disimpan.", "created")
        return redirect(url_for("detail_kk", kk_id=kk_id))
    except mysql.connector.IntegrityError:
        if conn: conn.rollback()
        flash("Nomor KK sudah terdaftar. Periksa kembali nomor yang dimasukkan.", "error")
        return render_confirm(filename, identity, members, status=409)
    except Exception:
        if conn: conn.rollback()
        app.logger.exception("Gagal menyimpan data KK.")
        flash("Data gagal disimpan ke database. Periksa MySQL lalu coba lagi.", "error")
        return render_confirm(filename, identity, members, status=500)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.route("/kk")
def daftar_kk():
    conn = cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("""SELECT kk.*, COUNT(a.id_anggota) AS total_anggota
            FROM tbl_identitasKK kk LEFT JOIN tbl_anggotaKeluargaKK a ON a.id_kk=kk.id_kk
            GROUP BY kk.id_kk ORDER BY kk.updated_at DESC, kk.id_kk DESC""")
        return render_template("daftar_kk.html", records=cur.fetchall())
    except Exception:
        app.logger.exception("Gagal memuat daftar KK.")
        flash("Daftar KK tidak dapat dimuat.", "error")
        return render_template("daftar_kk.html", records=[])
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.route("/kk/<int:kk_id>")
def detail_kk(kk_id):
    return render_template("detail_kk.html", kk=get_kk(kk_id))


@app.route("/kk/<int:kk_id>/edit", methods=["GET", "POST"])
def edit_kk(kk_id):
    kk = get_kk(kk_id)
    if request.method == "GET":
        return render_template("edit_kk.html", kk=kk, identitas_kk=kk, members=kk["anggota"],
            identity_fields=IDENTITY_FIELDS, member_fields=MEMBER_LABELS)
    try:
        identity, members = collect_form_data()
    except ValueError as error:
        flash(str(error), "error")
        return render_template("edit_kk.html", kk=kk, identitas_kk=request_identity(),
            members=request_members(), identity_fields=IDENTITY_FIELDS, member_fields=MEMBER_LABELS), 400
    conn = cur = None
    try:
        conn = get_db_connection()
        conn.start_transaction()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id_anggota FROM tbl_anggotaKeluargaKK WHERE id_kk=%s", (kk_id,))
        existing = {row["id_anggota"] for row in cur.fetchall()}
        submitted = set()
        assignments = ", ".join(f"{field}=%s" for field in IDENTITY_FIELDS)
        cur.execute(f"UPDATE tbl_identitasKK SET {assignments} WHERE id_kk=%s",
            (*[identity[field] for field in IDENTITY_FIELDS], kk_id))
        for member in members:
            member_id = member.pop("id_anggota", None)
            if member_id:
                member_id = int(member_id)
                if member_id not in existing:
                    raise ValueError("Data anggota tidak cocok dengan KK yang diedit.")
                assignments = ", ".join(f"{field}=%s" for field in MEMBER_FIELDS)
                cur.execute(f"UPDATE tbl_anggotaKeluargaKK SET {assignments} WHERE id_anggota=%s AND id_kk=%s",
                    (*[member[field] for field in MEMBER_FIELDS], member_id, kk_id))
                submitted.add(member_id)
            else:
                insert_members(cur, kk_id, [member])
                submitted.add(cur.lastrowid)
        removed = existing - submitted
        if removed:
            marks = ",".join(["%s"] * len(removed))
            cur.execute(f"DELETE FROM tbl_anggotaKeluargaKK WHERE id_kk=%s AND id_anggota IN ({marks})",
                (kk_id, *sorted(removed)))
        conn.commit()
        flash("Data KK berhasil diperbarui.", "success")
        return redirect(url_for("detail_kk", kk_id=kk_id))
    except ValueError as error:
        if conn: conn.rollback()
        flash(str(error), "error")
        return redirect(url_for("edit_kk", kk_id=kk_id))
    except mysql.connector.IntegrityError:
        if conn: conn.rollback()
        flash("Nomor KK tersebut sudah digunakan oleh data lain.", "error")
        return redirect(url_for("edit_kk", kk_id=kk_id))
    except Exception:
        if conn: conn.rollback()
        app.logger.exception("Gagal memperbarui data KK.")
        flash("Perubahan gagal disimpan. Periksa MySQL lalu coba lagi.", "error")
        return redirect(url_for("edit_kk", kk_id=kk_id))
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.route("/kk/<int:kk_id>/hapus", methods=["POST"])
def hapus_kk(kk_id):
    conn = cur = None
    missing = False
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM tbl_identitasKK WHERE id_kk=%s", (kk_id,))
        missing = cur.rowcount == 0
        conn.commit()
        if not missing:
            flash("Data KK dan seluruh anggotanya berhasil dihapus.", "success")
    except Exception:
        if conn: conn.rollback()
        app.logger.exception("Gagal menghapus KK.")
        flash("Data KK gagal dihapus.", "error")
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()
    if missing:
        abort(404)
    return redirect(url_for("daftar_kk"))


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


@app.route("/debug-ocr/<filename>")
def debug_ocr_file(filename):
    return send_from_directory(os.path.join(app.root_path, "debug_ocr"), filename)


@app.errorhandler(413)
def file_too_large(_error):
    flash("Ukuran gambar melebihi batas maksimal 5 MB.", "error")
    return redirect(url_for("upload"))


if __name__ == "__main__":
    app.run(debug=True)
