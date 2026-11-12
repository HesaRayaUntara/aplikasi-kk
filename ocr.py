import os
import re
import cv2
import easyocr
import numpy as np

from PIL import Image, ImageOps
from functools import lru_cache


# ==================================================
# 1. KONFIGURASI
# ==================================================

DEBUG_FOLDER = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "debug_ocr"
)

os.makedirs(DEBUG_FOLDER, exist_ok=True)

# ==========================================
# ERROR KHUSUS VALIDASI KUALITAS GAMBAR
# ==========================================

class ImageQualityError(Exception):
    pass


# Template berdasarkan format KK contoh.
# Koordinat menggunakan proporsi terhadap seluruh gambar.

TABLE_LAYOUTS = {

    "table_1": {

        "name": "Tabel Identitas Anggota",

        "x": (0.020, 0.978),
        "y": (0.181, 0.466),

        "header_ratio": 0.23,

        "columns": [
            "nomor",
            "nama_lengkap",
            "nik",
            "jenis_kelamin",
            "tempat_lahir",
            "tanggal_lahir",
            "agama",
            "pendidikan",
            "jenis_pekerjaan",
            "golongan_darah"
        ],

        "x_boundaries": [
            0.000,
            0.025,
            0.221,
            0.310,
            0.360,
            0.516,
            0.556,
            0.651,
            0.799,
            0.944,
            1.000
        ]

    },

    "table_2": {

        "name": "Tabel Status dan Orang Tua",

        "x": (0.020, 0.978),
        "y": (0.469, 0.754),

        "header_ratio": 0.25,

        "columns": [
            "nomor",
            "status_perkawinan",
            "tanggal_perkawinan",
            "status_hubungan",
            "kewarganegaraan",
            "no_paspor",
            "no_kitap",
            "nama_ayah",
            "nama_ibu"
        ],

        "x_boundaries": [
            0.000,
            0.025,
            0.168,
            0.230,
            0.340,
            0.436,
            0.515,
            0.593,
            0.814,
            1.000
        ]

    }

}

# Profil kedua untuk format KK yang kolom tabel pertamanya lebih lebar.
# Semua batas kolom dinormalisasi terhadap garis tepi tabel yang terdeteksi.
TABLE_LAYOUT_PROFILES = {
    "standard": {
        "table_1_columns": TABLE_LAYOUTS["table_1"]["x_boundaries"],
        "table_1_y": (0.181, 0.466),
        "table_1_header_ratio": 0.23,
        "table_2_y": (0.469, 0.754),
        "table_2_header_ratio": 0.25,
    },
    "wide_first_table": {
        "table_1_columns": [
            0.000, 0.020, 0.250, 0.352, 0.403, 0.504,
            0.565, 0.651, 0.800, 0.948, 1.000
        ],
        "table_1_y": (0.195, 0.433),
        "table_1_header_ratio": 0.235,
        "table_2_y": (0.438, 0.680),
        "table_2_header_ratio": 0.25,
    },
}


# ==================================================
# 2. INISIALISASI EASY OCR
# ==================================================

@lru_cache(maxsize=1)
def get_ocr_reader():

    return easyocr.Reader(
        ["id", "en"],
        gpu=False,
        verbose=False
    )


# ==================================================
# 3. MEMBACA GAMBAR
# ==================================================

def load_image(image_path):

    with Image.open(image_path) as original:

        image = ImageOps.exif_transpose(
            original
        ).convert("RGB")

        image = np.array(image)

    return cv2.cvtColor(
        image,
        cv2.COLOR_RGB2BGR
    )
    
    

# ==================================================
# 4. VALIDASI KUALITAS GAMBAR
# ==================================================

def validate_image_quality(image):
    """
    Memeriksa apakah gambar cukup layak untuk diproses OCR.
    Mengembalikan daftar masalah yang ditemukan.
    """

    issues = []

    height, width = image.shape[:2]

    # 1. Memeriksa resolusi gambar
    if width < 1000 or height < 700:
        issues.append(
            "Resolusi gambar terlalu kecil. "
            "Gunakan gambar dengan resolusi minimal 1000 x 700 piksel."
        )

    # Konversi ke grayscale
    gray = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2GRAY
    )

    # 2. Memeriksa ketajaman gambar
    sharpness = cv2.Laplacian(
        gray,
        cv2.CV_64F
    ).var()

    if sharpness < 50:
        issues.append(
            "Gambar terlalu buram. "
            "Silakan unggah gambar yang lebih tajam."
        )

    # 3. Memeriksa pencahayaan
    brightness = np.mean(gray)

    if brightness < 50:
        issues.append(
            "Gambar terlalu gelap. "
            "Pastikan pencahayaan cukup."
        )

    elif brightness > 220:
        issues.append(
            "Gambar terlalu terang. "
            "Hindari pantulan cahaya pada dokumen."
        )

    return issues



# ==================================================
# 4. DETEKSI KEMIRINGAN
# ==================================================

def detect_skew_angle(image):

    gray = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2GRAY
    )

    edges = cv2.Canny(
        gray,
        50,
        150
    )

    lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180,
        threshold=100,
        minLineLength=max(100, image.shape[1] // 5),
        maxLineGap=20
    )

    if lines is None:
        return 0.0

    lines = np.asarray(lines).reshape(-1, 4)

    angles = []

    for x1, y1, x2, y2 in lines:

        angle = np.degrees(
            np.arctan2(
                y2 - y1,
                x2 - x1
            )
        )

        if abs(angle) <= 7:
            angles.append(angle)

    if not angles:
        return 0.0

    return float(np.median(angles))


# ==================================================
# 5. PREPROCESSING GAMBAR
# ==================================================

def preprocess_image(image):

    angle = detect_skew_angle(image)

    height, width = image.shape[:2]

    if 0.3 < abs(angle) <= 7:

        matrix = cv2.getRotationMatrix2D(
            (width // 2, height // 2),
            angle,
            1.0
        )

        image = cv2.warpAffine(
            image,
            matrix,
            (width, height),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE
        )

    gray = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2GRAY
    )

    clahe = cv2.createCLAHE(
        clipLimit=2.0,
        tileGridSize=(8, 8)
    )

    enhanced = clahe.apply(gray)

    # Memperbesar gambar untuk OCR
    height, width = enhanced.shape

    if max(height, width) < 1800:

        scale = min(
            2.0,
            1800 / max(height, width)
        )

        enhanced = cv2.resize(
            enhanced,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC
        )

    return enhanced, angle


# ==================================================
# 6. DETEKSI GARIS TABEL
# ==================================================

def detect_table_lines(table_image):

    height, width = table_image.shape[:2]

    # Adaptive threshold
    binary = cv2.adaptiveThreshold(
        table_image,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        31,
        10
    )

    # ------------------------------
    # DETEKSI GARIS HORIZONTAL
    # ------------------------------

    horizontal_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (max(15, width // 25), 1)
    )

    horizontal = cv2.morphologyEx(
        binary,
        cv2.MORPH_OPEN,
        horizontal_kernel
    )

    horizontal_projection = np.sum(
        horizontal > 0,
        axis=1
    )

    horizontal_candidates = np.where(
        horizontal_projection > width * 0.25
    )[0]

    # ------------------------------
    # DETEKSI GARIS VERTIKAL
    # ------------------------------

    vertical_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (1, max(10, height // 15))
    )

    vertical = cv2.morphologyEx(
        binary,
        cv2.MORPH_OPEN,
        vertical_kernel
    )

    vertical_projection = np.sum(
        vertical > 0,
        axis=0
    )

    vertical_candidates = np.where(
        vertical_projection > height * 0.20
    )[0]

    # Menggabungkan koordinat yang berdekatan
    def merge_coordinates(coordinates, tolerance=4):

        if len(coordinates) == 0:
            return []

        groups = [[int(coordinates[0])]]

        for coordinate in coordinates[1:]:

            coordinate = int(coordinate)

            if coordinate - groups[-1][-1] <= tolerance:

                groups[-1].append(coordinate)

            else:

                groups.append([coordinate])

        return [
            int(np.mean(group))
            for group in groups
        ]

    horizontal_lines = merge_coordinates(
        horizontal_candidates
    )

    vertical_lines = merge_coordinates(
        vertical_candidates
    )

    return {

        "horizontal": horizontal_lines,

        "vertical": vertical_lines,

        "binary": binary,

        "horizontal_mask": horizontal,

        "vertical_mask": vertical

    }


# ==================================================
# 7. MEMBANTU MENENTUKAN BATAS BARIS
# ==================================================

def get_row_boundaries(
    table_height,
    header_ratio,
    detected_lines
):

    # Batas awal data setelah header
    data_start = int(
        table_height * header_ratio
    )

    # Batas akhir tabel
    data_end = table_height - 1

    # Ambil garis yang berada di area data
    candidates = [
        y for y in detected_lines
        if data_start - 5 <= y <= data_end
    ]

    # Tambahkan batas awal dan akhir
    candidates = sorted(
        set([data_start] + candidates + [data_end])
    )

    # Kita mengharapkan 11 batas untuk 10 baris.
    # Jika deteksi garis kurang lengkap atau berlebihan,
    # gunakan pembagian proporsional sebagai fallback.

    if len(candidates) != 11:

        return [
            int(
                data_start
                + i * (data_end - data_start) / 10
            )
            for i in range(11)
        ]

    return candidates


def select_layout_profile(image):
    """Pilih profil kolom yang paling cocok dengan garis tabel pertama."""

    height, width = image.shape[:2]
    x1 = int(width * 0.02)
    x2 = int(width * 0.978)
    y1 = int(height * 0.17)
    y2 = int(height * 0.47)

    table_region = image[y1:y2, x1:x2]
    vertical_lines = detect_table_lines(table_region)["vertical"]

    if len(vertical_lines) < 8:
        return "standard"

    grid_left = min(vertical_lines)
    grid_right = max(vertical_lines)
    grid_width = grid_right - grid_left

    if grid_width <= 0:
        return "standard"

    normalized_lines = [
        (line - grid_left) / grid_width
        for line in vertical_lines
    ]

    scores = {}
    for profile_name, profile in TABLE_LAYOUT_PROFILES.items():
        expected = profile["table_1_columns"][1:-1]
        distances = [
            min(abs(line - boundary) for line in normalized_lines)
            for boundary in expected
        ]
        scores[profile_name] = float(np.mean(distances))

    if scores["wide_first_table"] + 0.006 < scores["standard"]:
        return "wide_first_table"

    return "standard"


def map_page_detections_to_rows(
    raw_results,
    columns,
    crop_x,
    crop_y,
    x_boundaries,
    y_boundaries
):
    """Petakan hasil OCR satu halaman ke sel berdasarkan pusat bounding box."""

    rows = [{} for _ in range(10)]

    for row_index in range(10):
        y1 = crop_y + y_boundaries[row_index]
        y2 = crop_y + y_boundaries[row_index + 1]

        for column_index, column_name in enumerate(columns):
            x1 = crop_x + x_boundaries[column_index]
            x2 = crop_x + x_boundaries[column_index + 1]
            matches = []

            for bbox, text, confidence in raw_results:
                center_x = float(np.mean([point[0] for point in bbox]))
                center_y = float(np.mean([point[1] for point in bbox]))

                if x1 <= center_x < x2 and y1 <= center_y < y2:
                    text = text.strip()
                    if text:
                        matches.append((center_x, text, float(confidence)))

            matches.sort(key=lambda item: item[0])
            rows[row_index][column_name] = " ".join(
                item[1] for item in matches
            ).strip()
            rows[row_index][column_name + "_confidence"] = (
                float(np.mean([item[2] for item in matches]))
                if matches else 0.0
            )

    return rows


# ==================================================
# 8. OCR UNTUK SETIAP SEL
# ==================================================


def read_cell(reader, cell, column_name):

    if cell.size == 0:
        return {
            "text": "",
            "confidence": 0.0
        }

    # 1. Memperbesar gambar
    scale = 3

    cell = cv2.resize(
        cell,
        None,
        fx=scale,
        fy=scale,
        interpolation=cv2.INTER_CUBIC
    )

    # 2. Meningkatkan kontras
    clahe = cv2.createCLAHE(
        clipLimit=2.0,
        tileGridSize=(4, 4)
    )

    cell = clahe.apply(cell)

    # 3. Mengurangi noise
    cell = cv2.fastNlMeansDenoising(
        cell,
        None,
        h=10
    )

    # 4. Menambahkan margin putih
    cell = cv2.copyMakeBorder(
        cell,
        20,
        20,
        20,
        20,
        cv2.BORDER_CONSTANT,
        value=255
    )

    # 5. Konfigurasi OCR
    numeric_columns = {
        "nik",
        "tanggal_lahir",
        "tanggal_perkawinan"
    }

    kwargs = {
        "detail": 1,
        "paragraph": False,
        # Beamsearch pada versi EasyOCR terpasang menghasilkan overflow
        # dan bacaan buruk pada sel KK; greedy lebih stabil untuk sel pendek.
        "decoder": "greedy",
        "contrast_ths": 0.05,
        "adjust_contrast": 0.7,
        "text_threshold": 0.5,
        "low_text": 0.3
    }

    if column_name in numeric_columns:
        kwargs["allowlist"] = "0123456789-./"

    # 6. Membaca teks
    results = reader.readtext(
        cell,
        **kwargs
    )

    if not results:
        return {
            "text": "",
            "confidence": 0.0
        }

    texts = []
    confidences = []

    for bbox, text, confidence in results:

        text = text.strip()

        if text:
            texts.append(text)
            confidences.append(float(confidence))

    return {
        "text": " ".join(texts).strip(),
        "confidence": (
            float(np.mean(confidences))
            if confidences else 0.0
        )
    }



# ==================================================
# OCR BATCH UNTUK SEKUMPULAN SEL
# ==================================================

def read_cells_batch(reader, cells, column_name):
    """
    Membaca kumpulan sel satu per satu.
    Nama fungsi dipertahankan agar pemanggilan di process_table()
    tidak perlu diubah. Tidak menggunakan readtext_batched().
    """

    output = []

    for cell in cells:
        result = read_cell(
            reader,
            cell,
            column_name
        )
        output.append(result)

    return output


# ==================================================
# 9. SEGMENTASI DAN PEMBACAAN TABEL
# ==================================================

def process_table(
    image,
    layout,
    debug_name,
    raw_results
):

    height, width = image.shape[:2]

    # Crop berdasarkan template
    x_start = int(width * layout["x"][0])
    x_end = int(width * layout["x"][1])

    y_start = int(height * layout["y"][0])
    y_end = int(height * layout["y"][1])

    table_image = image[
        y_start:y_end,
        x_start:x_end
    ]

    table_height, table_width = table_image.shape[:2]

    # Deteksi garis tabel
    line_data = detect_table_lines(
        table_image
    )

    detected_vertical = line_data["vertical"]

    # Garis tepi tabel lebih akurat daripada tepi crop gambar.
    if len(detected_vertical) >= 2:
        grid_left = min(detected_vertical)
        grid_right = max(detected_vertical)
    else:
        grid_left = 0
        grid_right = table_width - 1

    grid_width = max(1, grid_right - grid_left)
    x_boundaries = [
        int(grid_left + value * grid_width)
        for value in layout["x_boundaries"]
    ]

    # Sesuaikan batas template ke garis vertikal terdekat.
    tolerance = max(5, int(grid_width * 0.025))

    for index in range(1, len(x_boundaries) - 1):

        expected_x = x_boundaries[index]

        nearby_lines = [
            x for x in detected_vertical
            if abs(x - expected_x) <= tolerance
        ]

        if nearby_lines:

            best_line = min(
                nearby_lines,
                key=lambda x: abs(x - expected_x)
            )

            x_boundaries[index] = best_line

    x_boundaries[0] = grid_left
    x_boundaries[-1] = grid_right
    x_boundaries = sorted(x_boundaries)

    # Batas baris berdasarkan garis horizontal
    y_boundaries = get_row_boundaries(
        table_height,
        layout["header_ratio"],
        line_data["horizontal"]
    )

    rows = map_page_detections_to_rows(
        raw_results,
        layout["columns"],
        x_start,
        y_start,
        x_boundaries,
        y_boundaries
    )

    # Visualisasi garis deteksi
    debug_image = cv2.cvtColor(
        table_image,
        cv2.COLOR_GRAY2BGR
    )

    # Menggambar garis horizontal
    for y in y_boundaries:

        cv2.line(
            debug_image,
            (0, y),
            (table_width - 1, y),
            (0, 255, 0),
            1
        )

    # Menggambar garis vertikal
    for x in x_boundaries:

        cv2.line(
            debug_image,
            (x, 0),
            (x, table_height - 1),
            (255, 0, 0),
            1
        )

    cv2.imwrite(
        os.path.join(
            DEBUG_FOLDER,
            f"{debug_name}_deteksi.png"
        ),
        debug_image
    )

    
    # Simpan crop sel untuk inspeksi visual; teksnya dipetakan dari OCR halaman.
    for column_index, column_name in enumerate(
        layout["columns"]
    ):

        x1 = x_boundaries[column_index]
        x2 = x_boundaries[column_index + 1]

        cells = []

        # Mengambil potongan gambar dari 10 baris
        for row_index in range(10):

            y1 = y_boundaries[row_index]
            y2 = y_boundaries[row_index + 1]

            padding = 2

            cell = table_image[
                y1 + padding:y2 - padding,
                x1 + padding:x2 - padding
            ]

            cells.append(cell)
            
            
        # DEBUG: Simpan seluruh potongan sel untuk pemeriksaan
        for debug_index, debug_cell in enumerate(cells):
            if debug_cell.size > 0:
                debug_path = os.path.join(
                    DEBUG_FOLDER,
                    f"{debug_name}_{column_name}_baris{debug_index + 1}.png"
                )
                cv2.imwrite(debug_path, debug_cell)


    return {

        "rows": rows,

        "detected_horizontal": len(
            line_data["horizontal"]
        ),

        "detected_vertical": len(
            line_data["vertical"]
        ),

        "row_boundaries": y_boundaries,

        "x_boundaries": x_boundaries,

        "debug_image": f"{debug_name}_deteksi.png"

    }


# ==================================================
# 10. OCR HEADER IDENTITAS KK
# ==================================================

def process_identity(image, reader):

    height, width = image.shape[:2]

    # Crop bagian header
    identity = image[
        int(height * 0.06):int(height * 0.18),
        int(width * 0.02):int(width * 0.98)
    ]

    results = reader.readtext(
        identity,
        detail=1,
        paragraph=False,
        decoder="greedy"
    )

    items = []

    for bbox, text, confidence in results:

        items.append({

            "text": text,

            "confidence": float(confidence)

        })

    return items


def parse_identity_fields(image, raw_results, reader):
    """Map OCR detections in the document header/footer to KK identity fields."""
    height, width = image.shape[:2]
    detections = []
    for bbox, text, confidence in raw_results:
        cx = float(np.mean([point[0] for point in bbox])) / width
        cy = float(np.mean([point[1] for point in bbox])) / height
        detections.append((cx, cy, str(text).strip(), float(confidence)))

    fields = {
        "no_kk": "", "kepala_keluarga": "", "alamat": "", "rt": "", "rw": "",
        "desa_kelurahan": "", "kecamatan": "", "kabupaten_kota": "", "provinsi": "",
        "kode_pos": "", "tanggal_dikeluarkan": "",
    }
    labels = {
        "kepala_keluarga": (("namakepalakeluarga",), .06, .21),
        "alamat": (("alamat",), .06, .21), "rt_rw": (("rtrw", "rtirw", "rt/rw"), .06, .21),
        "kode_pos": (("kodepos",), .06, .21),
        "desa_kelurahan": (("desakelurahan", "desalkelurahan"), .06, .21),
        "kecamatan": (("kecamatan",), .06, .21),
        "kabupaten_kota": (("kabupatenkota",), .06, .21),
        "provinsi": (("provinsi",), .06, .21),
        "tanggal_dikeluarkan": (("dikeluarkantanggal", "dikeluarkantgl"), .68, .84),
    }
    normalize = lambda value: re.sub(r"[^a-z]", "", value.lower())
    for field, (variants, min_y, max_y) in labels.items():
        candidates = []
        for lx, ly, label_text, _ in detections:
            compact = normalize(label_text)
            if any(compact == variant or (len(compact) >= 8 and compact in variant) for variant in variants) and min_y <= ly <= max_y:
                values = [(x, y, text) for x, y, text, _ in detections
                          if x > lx and abs(y - ly) < .008 and min_y <= y <= max_y]
                if values:
                    x, _, value = min(values, key=lambda item: item[0] - lx)
                    candidates.append((abs(ly - (min_y + max_y) / 2), ly, value))
        if candidates:
            fields[field] = min(candidates, key=lambda item: item[0])[2].strip(" :.-")

    for _, y, text, _ in detections:
        if y < .16:
            digits = re.sub(r"\D", "", text)
            if len(digits) == 16:
                fields["no_kk"] = digits
                break
    rt_rw = fields.pop("rt_rw", "")
    if rt_rw:
        parts = re.split(r"\s*[/\\-]\s*", rt_rw, maxsplit=1)
        fields["rt"] = re.sub(r"\D", "", parts[0])
        fields["rw"] = re.sub(r"\D", "", parts[1]) if len(parts) > 1 else ""

    # Tanggal terbit sering terlalu kecil untuk lolos deteksi OCR satu halaman.
    if not fields["tanggal_dikeluarkan"]:
        crop = image[int(height * .735):int(height * .795), int(width * .16):int(width * .29)]
        if crop.size:
            crop = cv2.resize(crop, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
            date_results = reader.readtext(crop, detail=1, paragraph=False, decoder="greedy",
                                           allowlist="0123456789-/.")
            for _, text, confidence in date_results:
                match = re.search(r"\d{1,2}[-/.]\d{1,2}[-/.]\d{4}", text)
                if match and confidence >= .45 and match.group(0) not in {item[2] for item in detections}:
                    fields["tanggal_dikeluarkan"] = match.group(0).replace("/", "-").replace(".", "-")
                    break
    return fields


# ==================================================
# 11. PENGGABUNGAN DUA TABEL
# ==================================================


def merge_member_tables(table_1, table_2):

    members = []

    for index in range(10):

        first = table_1["rows"][index]
        second = table_2["rows"][index]

        # Mengambil dan membersihkan nama serta NIK
        nama = first["nama_lengkap"].strip()
        nik = first["nik"].strip()

        # Menganggap nilai berikut sebagai data kosong
        placeholders = {"", "-", ".", "_"}

        nama_confidence = first["nama_lengkap_confidence"]
        nama_letters = re.sub(r"[^A-Za-z]", "", nama)
        nama_valid = (
            nama.upper() not in placeholders
            and len(nama_letters) >= 2
            and nama_confidence >= 0.20
        )

        # NIK harus terdiri dari 16 digit
        nik_digits = re.sub(r"\D", "", nik)
        nik_valid = len(nik_digits) == 16

        # Lewati baris yang tidak memiliki identitas anggota
        if not nama_valid and not nik_valid:
            continue

        member = {
            "nomor": index + 1,

            "nama_lengkap": nama,
            "nik": nik,

            "jenis_kelamin": first["jenis_kelamin"],
            "tempat_lahir": first["tempat_lahir"],
            "tanggal_lahir": first["tanggal_lahir"],
            "agama": first["agama"],
            "pendidikan": first["pendidikan"],
            "jenis_pekerjaan": first["jenis_pekerjaan"],
            "golongan_darah": first["golongan_darah"],

            "status_perkawinan": second["status_perkawinan"],
            "tanggal_perkawinan": second["tanggal_perkawinan"],
            "status_hubungan": second["status_hubungan"],
            "kewarganegaraan": second["kewarganegaraan"],
            "no_paspor": second["no_paspor"],
            "no_kitap": second["no_kitap"],
            "nama_ayah": second["nama_ayah"],
            "nama_ibu": second["nama_ibu"],

            "nik_confidence": first["nik_confidence"],
            "nama_confidence": nama_confidence
        }

        for field_name in (
            "nama_lengkap", "nik", "jenis_kelamin", "tempat_lahir",
            "tanggal_lahir", "agama", "pendidikan", "jenis_pekerjaan",
            "golongan_darah"
        ):
            member[field_name + "_confidence"] = first.get(
                field_name + "_confidence", 0.0
            )

        for field_name in (
            "status_perkawinan", "tanggal_perkawinan", "status_hubungan",
            "kewarganegaraan", "no_paspor", "no_kitap", "nama_ayah",
            "nama_ibu"
        ):
            member[field_name + "_confidence"] = second.get(
                field_name + "_confidence", 0.0
            )

        members.append(member)

    return members



# ==================================================
# 12. PROSES OCR UTAMA
# ==================================================

def process_kk_image(image_path):

    
    # Membaca gambar asli
    original = load_image(image_path)

    # Memeriksa kualitas gambar sebelum OCR
    quality_issues = validate_image_quality(original)

    if quality_issues:
        raise ImageQualityError(
            " ".join(quality_issues)
        )


    # Preprocessing
    processed, skew_angle = preprocess_image(
        original
    )

    height, width = processed.shape[:2]

    reader = get_ocr_reader()

    # OCR seluruh gambar untuk informasi mentah
    raw_results = reader.readtext(
        processed,
        detail=1,
        paragraph=False
    )

    detected_items = []

    for bbox, text, confidence in raw_results:

        x_coordinates = [p[0] for p in bbox]
        y_coordinates = [p[1] for p in bbox]

        center_x = float(np.mean(x_coordinates))
        center_y = float(np.mean(y_coordinates))

        detected_items.append({

            "text": text,

            "confidence": float(confidence),

            "center_x": center_x,

            "center_y": center_y,

            "x_percent": center_x / width * 100,

            "y_percent": center_y / height * 100

        })

    # Identitas KK
    identity_items = process_identity(
        processed,
        reader
    )

    identity_text = " ".join(
        item["text"]
        for item in identity_items
    )
    identity_data = parse_identity_fields(processed, raw_results, reader)

    # Pilih geometri tabel yang paling cocok dengan format dokumen.
    layout_profile = select_layout_profile(processed)
    profile = TABLE_LAYOUT_PROFILES[layout_profile]

    table_1_layout = dict(TABLE_LAYOUTS["table_1"])
    table_1_layout["x_boundaries"] = profile["table_1_columns"]
    table_1_layout["y"] = profile["table_1_y"]
    table_1_layout["header_ratio"] = profile["table_1_header_ratio"]

    table_2_layout = dict(TABLE_LAYOUTS["table_2"])
    table_2_layout["y"] = profile["table_2_y"]
    table_2_layout["header_ratio"] = profile["table_2_header_ratio"]

    # Tabel pertama
    table_1 = process_table(
        processed,
        table_1_layout,
        "tabel_1",
        raw_results
    )

    # Tabel kedua
    table_2 = process_table(
        processed,
        table_2_layout,
        "tabel_2",
        raw_results
    )
    
    # DEBUG: Menampilkan hasil OCR setiap kolom pada baris pertama
    print(f"\n========== PROFIL LAYOUT: {layout_profile} ==========")
    print("\n========== DEBUG TABEL 1 ==========")

    for key, value in table_1["rows"][0].items():
        print(f"{key}: {value}")

    print("\n========== DEBUG TABEL 2 ==========")

    for key, value in table_2["rows"][0].items():
        print(f"{key}: {value}")

    # Menggabungkan kedua tabel
    members = merge_member_tables(
        table_1,
        table_2
    )

    # Hasil OCR mentah
    full_text = "\n".join(
        item["text"]
        for item in detected_items
    )

    # Pengelompokan sederhana untuk kompatibilitas tampilan lama
    lines = []

    for item in detected_items:

        lines.append({

            "text": item["text"],

            "confidence": item["confidence"],

            "y_percent": round(
                item["y_percent"],
                2
            )

        })

    return {

        "full_text": full_text,

        "lines": lines,

        "total_text": len(detected_items),

        "image_width": width,

        "image_height": height,

        "skew_angle": round(skew_angle, 2),

        "identity_text": identity_text,

        "identity_data": identity_data,

        "identity_items": identity_items,

        "table_1": table_1,

        "table_2": table_2,

        "layout_profile": layout_profile,

        "members": members

    }
