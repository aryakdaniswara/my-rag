# V5 RAGAS Evaluation Dataset (Indonesian Main Set)

## Tujuan

Dataset `ui_main_v5_indonesian.json` disusun untuk mengevaluasi sistem RAG Universitas Indonesia pada pertanyaan yang dapat dijawab dari konteks terindeks. Versi ini menggunakan sumber chunk terbaru dari `ingest_job_20260508_merged_clean(1).json` dan mengikuti rancangan evaluasi yang lebih natural untuk chatbot helpdesk berbahasa Indonesia.

Fokus utama V5 adalah menguji apakah sistem dapat mengambil konteks Universitas Indonesia yang tepat, menjawab secara ringkas, menjaga kesetiaan terhadap konteks, dan tetap menggunakan bahasa Indonesia yang natural. `ground_truth` ditulis sebagai referensi utama RAGAS. Field `expected_answer` tetap dipertahankan untuk audit manual, tetapi bukan acuan utama apabila evaluator hanya membaca `ground_truth`.

## Prinsip Perancangan

1. Pertanyaan harus spesifik terhadap entitas yang ditanyakan, seperti jalur seleksi, program, sistem, biaya, layanan, dokumen, atau kontak resmi.
2. Pertanyaan tidak memakai rujukan tersembunyi seperti “ini”, “itu”, “tersebut”, “chunk ini”, atau “dokumen ini” tanpa menyebut objeknya secara jelas.
3. Pertanyaan ditulis dalam bahasa Indonesia yang natural, kecuali nama resmi seperti SIMAK UI, PPKB, Talent Scouting, KKI, RPL, UKT, IPI, URL, surel, skor tes, dan nominal biaya.
4. `ground_truth` ditulis dalam bahasa Indonesia dan hanya memuat fakta yang diperlukan untuk menjawab pertanyaan.
5. Nilai resmi seperti URL, surel, nomor SK, skor tes, dan nominal biaya dipertahankan sebagaimana sumber.
6. Pertanyaan yang terlalu berorientasi inspeksi dokumen, seperti hanya menanyakan banyak nomor SK atau tanggal penetapan, dibatasi.
7. Pertanyaan terkait pembayaran tidak meminta nomor rekening atau SWIFT secara langsung; evaluasi diarahkan pada metode pembayaran atau rujukan resmi.
8. Dataset mempertahankan cukup banyak pertanyaan `multi_chunk` agar kualitas retrieval tidak tampak terlalu mudah atau terinflasi.

## Skema Data

Setiap baris menggunakan skema berikut:

```json
{
  "id": "v5_001",
  "category": "admission_procedure",
  "scope": "single_chunk",
  "answer_type": "rule_or_eligibility",
  "question": "...",
  "ground_truth": "...",
  "expected_answer": ["..."],
  "source_chunk_ids": ["..."],
  "source_doc_ids": ["..."],
  "source_urls": ["..."]
}
```

## Definisi Scope

Dataset ini hanya menggunakan dua nilai `scope`:

| Scope | Definisi |
|---|---|
| `single_chunk` | Jawaban dirancang agar dapat dijawab dari satu chunk yang relevan. |
| `multi_chunk` | Jawaban dirancang agar perlu menggabungkan lebih dari satu potongan konteks, bagian, atau sumber terkait. Label ini tidak berarti harus tepat dua chunk. |

`scope` dipakai untuk membaca kompleksitas retrieval. Jika pertanyaan berbentuk perbandingan tetapi semua informasi berada dalam satu chunk, maka `scope` tetap `single_chunk` dan bentuk jawabannya dicatat pada `answer_type: comparison`.

## Komposisi Dataset

| Dimensi | Nilai | Jumlah |
|---|---|---:|
| Ukuran | Jumlah total pertanyaan | 60 |
| Scope | `single_chunk` | 45 |
| Scope | `multi_chunk` | 15 |
| Category | `admission_procedure` | 12 |
| Category | `tuition_fee` | 18 |
| Category | `program_info` | 11 |
| Category | `scholarship_info` | 8 |
| Category | `student_service_info` | 5 |
| Category | `official_reference` | 6 |

## Distribusi Answer Type

| Answer type | Jumlah |
|---|---:|
| `comparison` | 4 |
| `contact_or_system` | 4 |
| `date_or_period` | 4 |
| `definition` | 6 |
| `document_or_url` | 2 |
| `fee_amount` | 17 |
| `program_or_faculty` | 1 |
| `rule_or_eligibility` | 22 |

## Catatan Evaluasi

Dataset ini dibuat untuk evaluasi RAGAS yang menggunakan `ground_truth` sebagai referensi utama. Oleh karena itu, `ground_truth` ditulis lebih natural dan tidak terlalu bergantung pada variasi format seperti bahasa Inggris pada sumber. Sumber berbahasa Inggris tetap dapat digunakan apabila faktanya penting dan dapat dijawab dalam bahasa Indonesia secara wajar.

Dataset ini tidak dimaksudkan sebagai stress test ekstrem. Pertanyaan `multi_chunk` dipertahankan untuk menguji kemampuan retrieval dan sintesis ringan, tetapi mayoritas pertanyaan tetap `single_chunk` karena pertanyaan helpdesk nyata biasanya meminta satu fakta, aturan, kontak, biaya, atau prosedur yang jelas.
