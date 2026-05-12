# V5 RAGAS Evaluation Dataset

## Latar Belakang
V5 disusun sebagai penyempurnaan dari V4 dengan fokus pada kualitas, variasi, dan kemudahan audit manual. Dibandingkan versi sebelumnya yang lebih besar, V5 diperkecil menjadi 55 pertanyaan answerable agar pemeriksaan baris per baris, penelusuran ground truth, dan analisis kegagalan tetap praktis dilakukan.

## Tujuan
V5 bertujuan untuk mengevaluasi perilaku RAG pada pertanyaan yang benar-benar dapat dijawab dari basis pengetahuan terindeks. Fokus evaluasi diarahkan pada kemampuan sistem untuk mengambil konteks yang tepat, menjaga kesetiaan jawaban terhadap konteks, dan membedakan jalur, program, aturan biaya, serta dokumen resmi yang mirip.

## Prinsip Perancangan
V5 dirancang agar lebih seimbang, realistis, dan mudah diaudit secara manual. Pertanyaan biaya tetap dipertahankan karena cakupan sumber memang kuat pada dokumen biaya pendidikan, tetapi porsinya dikendalikan agar benchmark tidak berubah menjadi kumpulan lookup tabel SK semata. Porsi pertanyaan `shifted` dan `user_like` ditingkatkan agar variasi bahasa lebih mendekati penggunaan chatbot yang nyata, tanpa mengorbankan keterlacakan jawaban ke chunk sumber.

## Cakupan Kategori
V5 menggunakan empat kategori topikal yang sesuai dengan cakupan sumber yang tersedia:
- `Admission pathways`
- `Fees and financial information`
- `Academic/program information`
- `Official systems and contacts`

Pembagian ini dipilih agar kategori tetap berbasis topik nyata, sementara aspek ketahanan retrieval dan pembedaan lintas dokumen direpresentasikan melalui `scope_category`, terutama `cross_section`.

## Jenis Cakupan Pertanyaan
V5 menggunakan tiga jenis cakupan pertanyaan:
- `single_chunk`: jawaban dapat disokong oleh satu chunk yang jelas.
- `multi_chunk`: jawaban memerlukan penggabungan dua potongan konteks yang saling berkaitan erat.
- `cross_section`: jawaban memerlukan pembedaan lintas jalur, dokumen, bagian tabel, atau kategori program.

Pertanyaan `cross_section` dibatasi hanya 7 butir karena fungsinya sebagai subset robustness, bukan sebagai bentuk dominan dari benchmark utama.

## Gaya Perumusan Pertanyaan
V5 menggunakan tiga gaya perumusan:
- `near_source`: mendekati bunyi sumber untuk memeriksa retrieval langsung.
- `shifted`: parafrasa yang tetap jelas untuk menguji retrieval semantik.
- `user_like`: pertanyaan yang lebih natural seperti yang mungkin diajukan calon mahasiswa, orang tua, atau pengguna helpdesk.

Porsi `shifted` dan `user_like` diperbesar agar benchmark lebih representatif terhadap interaksi chatbot yang realistis.

## Komposisi Dataset

| Dimensi | Nilai | Jumlah |
|---|---|---:|
| Ukuran | Jumlah total pertanyaan | 55 |
| Ukuran | Pertanyaan answerable | 55 |
| Main category | Admission pathways | 14 |
| Main category | Fees and financial information | 20 |
| Main category | Academic/program information | 10 |
| Main category | Official systems and contacts | 11 |
| Scope category | single_chunk | 35 |
| Scope category | multi_chunk | 13 |
| Scope category | cross_section | 7 |
| Wording style | near_source | 11 |
| Wording style | shifted | 22 |
| Wording style | user_like | 22 |

## Kegunaan untuk Analisis
V5 membantu memisahkan beberapa jenis kegagalan secara lebih jelas. Pertanyaan `single_chunk` berguna untuk melihat ketepatan retrieval dasar dan ekstraksi fakta. Pertanyaan `multi_chunk` berguna untuk menilai apakah sistem mampu menggabungkan potongan konteks yang relevan tanpa memperluas jawaban secara berlebihan. Pertanyaan `cross_section` berguna untuk memeriksa apakah model tertukar antara jalur, dokumen, atau kategori yang mirip.

## Batasan
V5 tidak dimaksudkan sebagai representasi final seluruh domain layanan informasi Universitas Indonesia. Dataset ini juga tidak memasukkan refusal question atau pertanyaan yang memang tidak didukung sumber, karena fokusnya adalah evaluasi answerable-question untuk metrik RAGAS. Selain itu, karena cakupan snapshot didominasi oleh dokumen biaya dan dokumen resmi terkait, topik yang paling banyak terwakili tetap berada di sekitar jalur, biaya, program, dan dokumen resmi.
