import os
import re
import uuid
from flask import Flask, request, jsonify, render_template
import pytesseract
from PIL import Image
from pdf2image import convert_from_path
import fitz  # PyMuPDF — ekstraksi text digital PDF (lebih akurat dari OCR)

# Setup Tesseract path (Windows)
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.path.exists(TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

# Setup Poppler path for PDF scanning
POPPLER_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "poppler-21.11.0",
    "Library",
    "bin",
)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024


def clean_text(text):
    """Bersih teks dari noise OCR dan line breaks."""
    if not text:
        return ""
    # Hapus hyphenation di akhir baris
    text = text.replace("-\n", " ")
    text = text.replace("- ", " ")
    # Gabung baris baru jadi spasi
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def split_lines(text):
    """Split text by newline, clean each line."""
    return [l.strip() for l in text.split('\n') if l.strip()]


def extract_nama_perusahaan(text):
    """
    Ekstrak Nama Perusahaan dari dokumen NIB.
    Menangani format label:
    - "Nama Pelaku Usaha : CV ABC XYZ"
    - "NAMA PERUSAHAAN: PT ABC XYZ Tbk" 
    - "Dengan Nama PT ABC XYZ"
    - Multi-line (gabung baris terpotong)
    """
    if not text:
        return None
    
    if not text.strip():
        return None

    lines = split_lines(text)

    # Pattern prioritas 1: "Nama Pelaku Usaha" (format NIB terbaru)
    for i, line in enumerate(lines):
        up = line.upper().strip()
        
        if 'NAMA PELAKU USAHA' in up:
            # Gunakan regex untuk menangkap nama setelah label
            m = re.search(r'(?:NAMA PELAKU USAHA)\s*[:\s.\-]+\s*(.*)', line, re.IGNORECASE)
            if m:
                candidate = m.group(1).strip()
                
                # Concat beberapa baris jika nama panjang (multi-line)
                if 5 < len(candidate) < 100:
                    for j in range(i+1, min(i+5, len(lines))):
                        next_line = lines[j].strip()
                        if not next_line:
                            break
                        next_up = next_line.upper()
                        
                        # Stop jika ketemu field lain
                        if any(kw in next_up for kw in [
                            'ALAMAT KANTOR', 'ALAMAT:', 'NIB', 'STATUS', 
                            'KBLI', 'TELEPON', 'EMAIL', 'WEBSITE', 'MODAL',
                            'NOMOR INDUK', 'SKALA USAHA', 'PENANAMAN MODAL'
                        ]):
                            break
                        
                        # Cek apakah baris lanjutan (berhuruf besar atau ada PT/CV)
                        if next_line[0].isupper() and len(next_line) < 150:
                            candidate += ' ' + next_line
                        else:
                            break
                
                # Clean result
                candidate = re.sub(r'[\s\-\.]+$', '', candidate).strip()
                if len(candidate) > 5 and re.search(r'(PT|CV|Tbk|Ltd|Inc|Nama)\b', candidate, re.IGNORECASE):
                    return candidate
        
        # Pattern 2: Label "NAMA PERUSAHAAN"
        if 'NAMA PERUSAHAAN' in up:
            m = re.search(r'(?:NAMA\s*PERUSAHAAN)\s*[:\s.\-]+\s*(.*)', line, re.IGNORECASE)
            if m:
                candidate = m.group(1).strip()
                
                if 5 < len(candidate) < 100:
                    for j in range(i+1, min(i+5, len(lines))):
                        next_line = lines[j].strip()
                        if not next_line:
                            break
                        next_up = next_line.upper()
                        
                        if any(kw in next_up for kw in [
                            'ALAMAT KANTOR', 'ALAMAT:', 'NIB', 'STATUS', 
                            'KBLI', 'TELEPON', 'EMAIL', 'WEBSITE', 'MODAL'
                        ]):
                            break
                        
                        if next_line[0].isupper() and len(next_line) < 150:
                            candidate += ' ' + next_line
                        else:
                            break
                
                candidate = re.sub(r'[\s\-\.]+$', '', candidate).strip()
                if len(candidate) > 10 and re.search(r'(PT|CV|Tbk|Ltd|Inc)', candidate, re.IGNORECASE):
                    return candidate
        
        # Pattern 3: Baris berisi PT/CV/Tbk yang berdiri sendiri (nama perusahaan)
        if re.search(r'\b(?:PT|CV)\b', line, re.IGNORECASE):
            candidate = line.strip()
            if len(candidate) > 10 and candidate[0].isupper():
                # Cek apakah bukan field lain
                if not any(kw in up for kw in ['NAMA PERUSAHAAN', 'ALAMAT', 'NIB:', 'STATUS', 'NAMA PELAKU']):
                    return candidate

    return None


def extract_alamat_kantor(text):
    """
    Ekstrak Alamat Kantor dari dokumen NIB.
    Menangani format:
    - ALAMAT KANTOR: Jl. XYZ No. 123, RT 001/RW 002, Kelurahan XYZ, Kecamatan XYZ, Kota XYZ
    - Multi-line (baris address)
    """
    if not text:
        return None
    
    if not text.strip():
        return None

    full_text = text.replace("-\n", " ").replace("\n", " ")
    full_text = re.sub(r'\s+', ' ', full_text).strip()
    lines = split_lines(text)

        # Temukan posisi "ALAMAT KANTOR" atau "ALAMAT"
    alamat_start = -1
    first_part = None
    for i, line in enumerate(lines):
        up = line.upper()
        if 'ALAMAT KANTOR' in up or 'ALAMAT PERUSAHAAN' in up:
            alamat_start = i
            # Ambil text setelah label (tangani ALAMAT / ALAMAT KANTOR / ALAMAT PERUSAHAAN)
            m = re.search(r'(?:ALAMAT(?:\s*(?:KANTOR|PERUSAHAAN))?\s*[:\s.\-]+)\s*(.*)', line, re.IGNORECASE)
            if m:
                first_part = m.group(1).strip()
            break
        
    if alamat_start >= 0:
        # Gabung semua baris setelah label sampai field lain dimulai
        parts = []
        if first_part:
            parts.append(first_part)
        for j in range(alamat_start + 1, min(alamat_start + 8, len(lines))):
            next_line = lines[j].strip()
            if not next_line:
                continue
            next_up = next_line.upper()
            # Hentikan jika ketemu field lain yang jelas
            if any(kw in next_up for kw in ['NAMA PERUSAHAAN', 'NAMA:', 'NIB:', 'NIB ', 'STATUS', 
                                                'KBLI:', 'KBLI ', 'TELEPON', 'TLP:', 'EMAIL',
                                                'WEBSITE', 'JENIS USAHA', 'MODAL', 'SKALA']):
                break
            parts.append(next_line)
        
        full_addr = ' '.join(parts)
        # Hapus label "ALAMAT KANTOR:"
        full_addr = re.sub(r'(?:ALAMAT\s*KANTOR|ALAMAT\s*PERUSAHAAN|ALAMAT)[:\s.\-]+', '', 
                          full_addr, flags=re.IGNORECASE).strip()
        full_addr = re.sub(r'\s+', ' ', full_addr)
        
        # Pastikan ada kata kunci alamat
        if len(full_addr) > 15 and re.search(r'(Jl\.|Jalan|Rt/Rw|Kelurahan|Kecamatan|Kabupaten|Kota)', full_addr, re.IGNORECASE):
            return full_addr

    # Pattern label "ALAMAT:" saja
    for i, line in enumerate(lines):
        up = line.upper().strip()
        if up == 'ALAMAT:' or up == 'ALAMAT :':
            parts = [line]
            for j in range(i + 1, min(i + 6, len(lines))):
                next_line = lines[j].strip()
                if not next_line:
                    continue
                # Hentikan jika field lain jelas
                if any(kw in next_line.upper() for kw in ['NAMA PERUSAHAAN', 'NAMA:', 'NIB', 'STATUS', 'KBLI', 'TELEPON', 'EMAIL']):
                    break
                parts.append(next_line)
            
            full_addr = ' '.join(parts)
            full_addr = re.sub(r'ALAMAT\s*[:\s.\-]+', '', full_addr, flags=re.IGNORECASE).strip()
            full_addr = re.sub(r'\s+', ' ', full_addr)
            
            if len(full_addr) > 15 and any(kw in full_addr.upper() for kw in ['JL', 'JALAN', 'RT', 'RW', 'KELURAHAN', 'KECAMATAN']):
                return full_addr

    # Regex di full_text
    try:
        addr_patterns = [
            r'(?:ALAMAT(?:\s*KANTOR)?\s*[:\s.\-]+)([^\n]{20,}?(?:Jl\.|Jalan)\S[^\n]{5,}?(?:Kelurahan|Kecamatan|Kabupaten|Kota)[^\n]{0,200})',
            r'(ALAMAT\s*[:\s.\-]+\s*[^\n]{20,}?)$',
            r'(?:ALAMAT|Alamat)[:\s.\-]+([Jj]l\.|Jalan)[^\n]{20,}?(?:Kelurahan|Kecamatan|Kota|Kabupaten)',
        ]
        
        for pat in addr_patterns:
            m = re.search(pat, full_text, re.IGNORECASE)
            if m:
                addr = m.group(1).strip() if m.lastindex else m.group(0).strip()
                addr = re.sub(r'ALAMAT\s*[:\s.\-]+\s*', '', addr, flags=re.IGNORECASE)
                addr = re.sub(r'\s+', ' ', addr)
                if len(addr) > 15:
                    return addr
    except:
        pass

    # Pattern 4: Cari Jl / Jalan di area sekitar alamat
    try:
        if 'alam' in full_text.lower() and ('jalan' in full_text.lower() or 'jl.' in full_text.lower()):
            # Cari Jl./Jalan setelah kata ALAMAT
            m = re.search(r'(Jl\.?|Jalan)\s*([^\n]{10,}?(?:Kelurahan|Kecamatan|Kota|Kabupaten|RT|RW|\d{5})[^\n]{0,100})', 
                         full_text, re.IGNORECASE | re.DOTALL)
            if m:
                addr = m.group(0).strip()
                addr = re.sub(r'\s+', ' ', addr)
                if len(addr) > 20:
                    return addr
    except:
        pass

    return None


def extract_kbli_check(text):
    """Cek apakah KBLI 46511 atau 47411 ada di dokumen (halaman 2+)."""
    if not text:
        return []

    results = []
    # Cari semua "kata" digit (urutan digit yang dipisahkan non-digit).
    # Ini memisahkan kode KBLI (5 digit) dari NIB (13 digit) atau nomor telepon.
    digit_words = re.findall(r'(?<!\d)\d+(?!\d)', text)

    for kode in ["46511", "47411"]:
        # Terdeteksi jika ada "kata" digit 5-7 yang mengandung kode:
        # - 5 digit = kode persis
        # - 6-7 digit = toleransi OCR (1-2 digit ekstra, mis. "147411")
        # "kata" 8+ digit (NIB, telepon) tidak dianggap match -> hindari false positive
        found = any(
            w == kode or (5 < len(w) <= 7 and kode in w)
            for w in digit_words
        )
        results.append({"kode": kode, "terdeteksi": found})

    return results


def extract_nib_number(text):
    """Extract NIB number (13 digits)."""
    if not text:
        return None
    matches = re.findall(r"\b(\d{13})\b", text)
    return matches[0] if matches else None


def extract_digital_text(pdf_path, start_page=None, end_page=None):
    """Extract text langsung dari PDF digital menggunakan PyMuPDF.
    Lebih cepat dan akurat dari OCR untuk PDF yang sudah punya text layer.
    """
    try:
        doc = fitz.open(pdf_path)
        total = len(doc)
        start = (start_page or 1) - 1
        end = end_page if end_page else total
        texts = []
        for i in range(start, min(end, total)):
            texts.append(doc[i].get_text())
        doc.close()
        raw = "\n\n".join(texts).strip()
        return normalize_digital_text(raw)
    except Exception:
        return ""


def normalize_digital_text(text):
    """Normalize text PDF digital: gabung 'Label\\n: Value' jadi 'Label : Value'.
    PyMuPDF sering memisah label dan nilai ke baris terpisah (label di baris sendiri,
    nilai di baris berikutnya dimulai dengan ':'). Ini menyebabkan regex extraction
    gagal. Fungsi ini menggabungkan kembali supaya format sama seperti OCR.
    """
    if not text:
        return text
    lines = text.split('\n')
    merged = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if i + 1 < len(lines) and re.match(r'^\s*[:：]', lines[i + 1]):
            merged.append(line.rstrip() + ' ' + lines[i + 1].strip())
            i += 2
        else:
            merged.append(line)
            i += 1
    return '\n'.join(merged)


def extract_from_pages(pdf_path, start_page=1, end_page=None):
    """Extract text dari semua halaman PDF.
    Coba digital extraction (PyMuPDF) dulu, fallback ke OCR untuk scanned PDF.
    """
    # 1. Coba digital extraction (PyMuPDF)
    text = extract_digital_text(pdf_path, start_page=start_page, end_page=end_page)
    if text and len(text.strip()) > 50:
        return text

    # 2. Fallback: OCR semua halaman
    try:
        if end_page is None:
            images = convert_from_path(
                pdf_path, dpi=300, poppler_path=POPPLER_PATH
            )
        else:
            images = convert_from_path(
                pdf_path, dpi=300, poppler_path=POPPLER_PATH,
                first_page=start_page, last_page=end_page
            )
        if not images:
            return ""
        texts = []
        for img in images:
            txt = pytesseract.image_to_string(img, lang="ind+eng")
            texts.append(txt.strip())
        return "\n\n".join(texts)
    except Exception:
        return ""


def process_file(file):
    """Process uploaded file dan extract data NIB.
    Halaman 1: Nama Perusahaan + Alamat Kantor
    Semua halaman: KBLI 46511/47411
    """
    filename = file.filename
    ext = os.path.splitext(filename)[1].lower()

    # Save temp
    temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads_temp")
    os.makedirs(temp_dir, exist_ok=True)
    unique_name = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(temp_dir, unique_name)
    file.save(file_path)

    result = {
        "doc_type": "unknown",
        "nama_pelaku_usaha": None,
        "alamat_kantor": None,
        "kbli": [{"kode": "46511", "terdeteksi": False}, {"kode": "47411", "terdeteksi": False}],
    }

    text = None
    doc_type = None
    all_text = None

    if ext == ".pdf":
        # 1. Coba digital extraction (PyMuPDF) untuk halaman 1
        try:
            digital_text = extract_digital_text(file_path, start_page=1, end_page=1)
            if digital_text and len(digital_text.strip()) > 50:
                doc_type = "digital"
                text = digital_text
                # Ambil semua halaman untuk KBLI
                all_text = extract_from_pages(file_path)
        except Exception:
            pass

        # 2. Jika digital gagal / scanned PDF -> OCR dengan Tesseract
        if not text or len(text.strip()) < 50:
            try:
                # OCR halaman 1 (untuk nama & alamat)
                images_page1 = convert_from_path(
                    file_path, dpi=300, poppler_path=POPPLER_PATH,
                    first_page=1, last_page=1
                )
                if images_page1:
                    doc_type = "scanned"
                    text = pytesseract.image_to_string(images_page1[0], lang="ind+eng")

                    # OCR semua halaman (untuk KBLI)
                    images_all = convert_from_path(
                        file_path, dpi=300, poppler_path=POPPLER_PATH
                    )
                    if images_all and len(images_all) > 1:
                        all_texts = [pytesseract.image_to_string(img, lang="ind+eng") for img in images_all]
                        all_text = "\n\n".join(all_texts)
                    else:
                        all_text = text
            except Exception:
                pass

    elif ext in (".png", ".jpg", ".jpeg"):
        doc_type = "image"
        try:
            text = pytesseract.image_to_string(Image.open(file_path), lang="ind+eng")
            all_text = text
        except Exception:
            pass

    # Proses text
    if text and len(text.strip()) > 10:
        result["doc_type"] = doc_type
        
        # Extract NIB
        nib = extract_nib_number(text)
        result["nib"] = nib

        # Extract company name (dari halaman 1)
        nama = extract_nama_perusahaan(text)
        result["nama_pelaku_usaha"] = nama

        # Extract address (dari halaman 1)
        alamat = extract_alamat_kantor(text)
        result["alamat_kantor"] = alamat

        # Check KBLI (dari SEMUA halaman, bukan cuma halaman 1)
        kbli_text = all_text if all_text else text
        result["kbli"] = extract_kbli_check(kbli_text)

        # OSS Verification
        if nib:
            oss_result = verify_nib(nib)
            if oss_result.get("success"):
                data = oss_result.get("data", {})
                result["verifikasi"] = {
                    "attempted": True,
                    "success": True,
                    "nib": nib,
                    "nama_perusahaan": data.get("perusahaan", ""),
                    "status_aktif": data.get("status", ""),
                    "status_migrasi": data.get("migrasi", ""),
                    "penanaman_modal": data.get("modal", ""),
                    "skala_usaha": data.get("skala", ""),
                }
            else:
                result["verifikasi"] = {
                    "attempted": True,
                    "success": False,
                    "nib": nib,
                    "error": oss_result.get("error_details", "Verification failed"),
                }
        else:
            result["verifikasi"] = {
                "attempted": False,
                "error": "NIB not found in document",
            }
    else:
        result["doc_type"] = "error"

    # Cleanup
    try:
        os.remove(file_path)
    except Exception:
        pass

    return result


def extract_from_pdf(pdf_path):
    """Extract text dari halaman pertama PDF.
    Coba digital extraction (PyMuPDF) dulu, fallback ke OCR untuk scanned PDF.
    """
    # 1. Coba digital extraction (PyMuPDF) — akurat untuk PDF digital
    text = extract_digital_text(pdf_path, start_page=1, end_page=1)
    if text and len(text.strip()) > 50:
        return text

    # 2. Fallback: OCR halaman 1 dengan lang="ind+eng"
    try:
        images = convert_from_path(
            pdf_path, dpi=300, poppler_path=POPPLER_PATH,
            first_page=1, last_page=1
        )
        if images:
            return pytesseract.image_to_string(images[0], lang="ind+eng")
    except Exception:
        pass
    return None


def verify_nib(nib_number):
    """Verify NIB di OSS.go.id."""
    return {
        "success": False,
        "error_details": "OSS.go.id pakai Cloudflare CAPTCHA. Verifikasi manual di: https://oss.go.id/id/verifikasi-nib",
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No file selected"}), 400

    result = process_file(file)
    return jsonify(result)


# --- Test sederhana di terminal ---
if __name__ == "__main__":
    import webbrowser
    import threading
    import sys

    # TEST jika ada argumen path file PDF
    if len(sys.argv) > 1:
        test_path = sys.argv[1]
        if os.path.exists(test_path):
            print("\n" + "=" * 60)
            print("  TESTING EXTRACTION")
            print("=" * 60)
            print(f"\nFile: {test_path}\n")
            
            # Extract text
            if test_path.lower().endswith('.pdf'):
                text = extract_from_pdf(test_path)
                all_text = extract_from_pages(test_path)
            elif test_path.lower().endswith(('.png', '.jpg', '.jpeg')):
                text = pytesseract.image_to_string(Image.open(test_path), lang="ind+eng")
                all_text = text
            else:
                print("Format tidak didukung. Gunakan .pdf atau gambar.")
                sys.exit(1)
            
            if text:
                # Test Nama (dari halaman 1)
                nama = extract_nama_perusahaan(text)
                print(f"[+] Nama Perusahaan: {nama}")
            
            # Test Alamat
            alamat = extract_alamat_kantor(text)
            print(f"[+] Alamat Kantor: {alamat}")
            
            # Test KBLI (dari semua halaman)
            kbli_check = extract_kbli_check(all_text if all_text else text)
            print("\n[+] KBLI Check:")
            for item in kbli_check:
                status = "DETEKSI" if item['terdeteksi'] else "TIDAK DITEMUKAN"
                print(f"    - {item['kode']}: {status}")
            
            print("\n" + "=" * 60)
            sys.exit(0)

    # Jalankan Flask app
    print("=" * 60)
    print("  TDI E-NIB Checker")
    print("=" * 60)
    print()
    print("  App running at: http://127.0.0.1:5000")
    print("  Test file: python app.py C:\\path\\to\\file.pdf")
    print("=" * 60)

    threading.Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:5000")).start()
    app.run(debug=True, port=5000)
