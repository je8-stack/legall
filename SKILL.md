---
name: ocr-scanned-pdf
description: Use when extracting data from scanned PDF documents (NIB / Nomor Induk Berusaha) via OCR. Triggers on upload of scanned PDF, image-based PDF, or when PyMuPDF digital extraction returns empty/short text. Covers Tesseract OCR configuration, page-by-page extraction workflow, and KBLI 46511/47411 detection across all pages.
---

# OCR Scanned PDF — NIB Data Extraction

Skill untuk mengekstrak informasi dari **scanned PDF** (PDF hasil scan / PDF gambar, bukan PDF digital) menggunakan Tesseract OCR.

## Kapan digunakan

Gunakan skill ini ketika:
- User upload file PDF yang **scanned** (gambar, bukan text layer)
- `extract_digital_text()` (PyMuPDF) mengembalikan text kosong atau < 50 karakter
- User upload gambar (`.png`, `.jpg`, `.jpeg`) sebagai pengganti PDF
- User melaporkan hasil ekstraksi salah/ kosong saat upload scanned PDF

## Prasyarat sistem

| Komponen       | Path / Install                                          |
| -------------- | ------------------------------------------------------- |
| Tesseract OCR  | `C:\Program Files\Tesseract-OCR\tesseract.exe`         |
| Bahasa Tesseract | `ind` (Indonesia) + `eng` (English) — `lang="ind+eng"` |
| Poppler         | `./poppler-21.11.0/Library/bin/`                       |
| PyMuPDF (fitz)  | Untuk cek apakah PDF digital atau scanned               |

Jika Tesseract tidak ada di path default, set `pytesseract.pytesseract.tesseract_cmd` ke path yang benar.

## Alur ekstraksi

```
Upload PDF
    |
    v
[1] Coba PyMuPDF (extract_digital_text) — halaman 1
    |
    |-- text > 50 char? --> doc_type = "digital"
    |                       text = digital_text
    |                       all_text = extract_from_pages(semua halaman)
    |
    |-- text < 50 char? --> PDF adalah SCAN
    |
    v
[2] OCR dengan Tesseract (lang="ind+eng") — halaman 1
    |-- doc_type = "scanned"
    |-- text = OCR page 1
    |-- all_text = OCR semua halaman
    |
    v
[3] Extract data dari text
    |-- Halaman 1: Nama Perusahaan + Alamat Kantor
    |-- Semua halaman: KBLI 46511 / 47411
    |
    v
[4] Return JSON ke frontend
```

## Halaman 1 — Ekstraksi Nama & Alamat

### Nama Perusahaan (`extract_nama_perusahaan`)

Cari label berikut di text halaman 1 (prioritas dari atas ke bawah):

1. **`Nama Pelaku Usaha`** — format NIB terbaru
   - Pattern: `Nama Pelaku Usaha : CV CINTA ALAM RAYA`
   - Jika label dan nilai di baris berbeda (PyMuPDF format):
     ```
     1. Nama Pelaku Usaha
     : CV CINTA ALAM RAYA
     ```
     `normalize_digital_text()` akan menggabungkan jadi: `1. Nama Pelaku Usaha : CV CINTA ALAM RAYA`

2. **`NAMA PERUSAHAAN`** — format alternatif
   - Pattern: `NAMA PERUSAHAAN: PT ABC XYZ Tbk`

3. **Baris dengan PT/CV** — fallback
   - Cari baris yang mengandung `PT` atau `CV` dan bukan field label lain

**Stop条件** untuk multi-line extraction:
- `ALAMAT KANTOR`, `ALAMAT:`, `NIB`, `STATUS`, `KBLI`, `TELEPON`, `EMAIL`, `WEBSITE`, `MODAL`

### Alamat Kantor (`extract_alamat_kantor`)

Cari label berikut di text halaman 1:

1. **`ALAMAT KANTOR`** — label utama
2. **`ALAMAT PERUSAHAAN`** — label alternatif
3. **`ALAMAT:`** — label singkat

Setelah label ditemukan, gabung baris berikutnya sampai ketemu field lain:
- `NAMA PERUSAHAAN`, `NAMA:`, `NIB:`, `STATUS`, `KBLI:`, `TELEPON`, `TLP:`, `EMAIL`, `WEBSITE`, `JENIS USAHA`, `MODAL`, `SKALA`

Validasi: alamat harus mengandung minimal salah satu:
`Jl.`, `Jalan`, `RT/RW`, `Kelurahan`, `Kecamatan`, `Kabupaten`, `Kota`

## Halaman 2+ — Deteksi KBLI

### KBLI yang dicari

| Kode   | Deskripsi                                  |
| ------ | ------------------------------------------ |
| 46511  | Perdagangan eceran lainnya                 |
| 47411  | Perdagangan eceran selain di tempat        |

### Logika deteksi (`extract_kbli_check`)

1. Cari semua "kata digit" (urutan digit yang dipisahkan non-digit) di text **semua halaman**
2. Untuk setiap kode KBLI, cek apakah ada "kata digit" 5-7 digit yang mengandung kode tersebut:
   - **5 digit** = kode persis (`46511`, `47411`)
   - **6-7 digit** = toleransi OCR (`147411` — nomor baris menempel)
   - **8+ digit** = NIB / nomor telepon — **tidak dianggap match** (hindari false positive)
3. Hasil: `{"kode": "47411", "terdeteksi": true/false}`

### Tampilan frontend

| Status           | Badge                                    |
| ---------------- | ---------------------------------------- |
| Ditemukan        | `✅` hijau + badge `TERDAFTAR`           |
| Tidak ditemukan  | `❌` merah + badge `TIDAK DITEMUKAN`   |

## OCR tips untuk hasil terbaik

1. **DPI**: Gunakan `dpi=300` untuk konversi PDF ke image (dengan Poppler)
2. **Bahasa**: Selalu `lang="ind+eng"` untuk dokumen Indonesia
3. **Preprocessing** (jika OCR kualitas rendah):
   - Convert ke grayscale: `img.convert('L')`
   - Naikkan DPI ke `400` atau `500`
   - Crop region spesifik jika field tidak terbaca
4. **False positive KBLI**: Jangan gunakan substring match sederhana (`kode in text`) — akan match di NIB 13 digit atau nomor telepon. Gunakan pendekatan "kata digit" 5-7 digit.

## Testing

Jalankan test di terminal dengan path file PDF:

```powershell
python app.py "C:\path\to\file.pdf"
```

Output:
```
[+] Nama Perusahaan: CV CINTA ALAM RAYA
[+] Alamat Kantor: K. Candra Kirana, Desa/Kelurahan Attakkae, ...
[+] KBLI Check:
    - 46511: TIDAK DITEMUKAN
    - 47411: DETEKSI
```

## File references

| File          | Fungsi                                      |
| ------------- | ------------------------------------------- |
| `app.py:43`   | `extract_nama_perusahaan()`                 |
| `app.py:136`  | `extract_alamat_kantor()`                   |
| `app.py:250`  | `extract_kbli_check()`                      |
| `app.py:275`  | `extract_digital_text()` — PyMuPDF          |
| `app.py:298`  | `normalize_digital_text()` — merge label    |
| `app.py:324`  | `extract_from_pages()` — digital + OCR      |
| `app.py:355`  | `process_file()` — orchestrator             |
| `app.py:449`  | `extract_from_pdf()` — page 1 digital+OCR   |
