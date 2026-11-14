# Báo cáo cá nhân — Day 06: Data Ingestion Engineering

## Thông tin học viên

- Họ và tên: Đặng Khắc Hoàng Minh
- MSSV: 2A202604082
- Lớp: L3B
- Repo: https://github.com/dangkhacm-a11y/K5-L3B-Day06-DangKhacHoangMinh-04082-DataIngestionEngineering
- Chủ đề: Data ingestion cho truy xuất tri thức; corpus là phần trích 61 trang từ *College Success* của OpenStax.

## Dữ liệu và pipeline

- **Nguồn và quyền sử dụng:** *College Success*, OpenStax, CC BY-NC-SA 4.0. Manifest ghi nguồn, URL, giấy phép và quy tắc đếm trang. PDF trích gồm 61 trang vật lý; cả 61 trang đều có văn bản trích xuất được và được tính là nội dung. Số trang trong benchmark là số trang vật lý của PDF trích, không phải số trang in của toàn bộ sách.
- **Đọc và chuẩn hóa:** `pypdf` trích văn bản theo từng trang. Mã Python chuẩn hóa Unicode NFC, bỏ soft hyphen, chuẩn hóa xuống dòng và khoảng trắng, nhưng giữ ranh giới đoạn. Trang và source ID được giữ để truy xuất nguồn. Không dùng OCR. Một số ký tự trong PDF được trích thành ký tự thay thế; đây là giới hạn của bản trích xuất.
- **Embedding:** OpenAI `text-embedding-3-small`, 1536 chiều; cùng model dùng cho document và query. Phiên bản provider không được pin riêng ngoài tên model.
- **Vector store:** PostgreSQL 16.16 và pgvector 0.8.7, cosine distance. Setup: `docker compose -p day6_student_starter up -d --wait`. Chạy pipeline từ `starter/` bằng `python -m src.run`.
- **Metadata:** `document_id`, `source`, `page` và `chapter`. Trường filter là `chapter` (số nguyên 1–3), gán theo ranh giới chương đã ghi trong manifest. Metadata `section` cũng được giữ để hỗ trợ truy vết; thử nghiệm filter chỉ dùng chapter.

## Cấu hình và benchmark

- **A:** cửa sổ cố định tối đa 500 ký tự, overlap 50 ký tự.
- **B:** gom các đoạn văn liền nhau tối đa 900 ký tự; đoạn dài hơn giới hạn được cắt thành các phần tối đa 900 ký tự.
- **C:** cùng chunk và embedding như B; áp dụng filter chapter khi câu hỏi có filter. Vì B và C dùng cùng chunk, vector của B được tái sử dụng cho C.
- Benchmark có 20 câu, chia 15 dev / 5 test; 6 câu có metadata filter. Mỗi câu lưu đáp án kỳ vọng, gold source/page và evidence quote. Evidence đã được đối chiếu với văn bản trích xuất trên trang đã ghi trước khi chạy.
- Bộ câu hỏi và split được cố định trước lần chạy; không điều chỉnh chiến lược sau khi xem test. Tuy nhiên, tiêu chí chọn chiến lược chưa được ghi lại trước khi xem kết quả test. Vì vậy, kết quả test được báo cáo thận trọng; tiêu chí hậu nghiệm là ưu tiên Evidence Hit@3 trên dev, sau đó xem coherence và khả năng tuân thủ filter.

## Kết quả retrieval

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Số chunk | Thời gian (s) | Chi phí API |
|---|---|---:|---:|---:|---:|---|
| A | Dev | 9/15 | 10/15 | 407 | 8.002 | Không ghi nhận token/chi phí |
| A | Test | 3/5 | 3/5 | 407 | 8.002 | Không ghi nhận token/chi phí |
| B | Dev | 9/15 | 11/15 | 221 | 4.567 | Không ghi nhận token/chi phí |
| B | Test | 4/5 | 4/5 | 221 | 4.567 | Không ghi nhận token/chi phí |
| C | Dev | 9/15 | 11/15 | 221 | 1.108 | Không ghi nhận token/chi phí |
| C | Test | 4/5 | 4/5 | 221 | 1.108 | Không ghi nhận token/chi phí |

Thời gian C không bao gồm tạo embedding tài liệu vì C tái sử dụng vector của B; không nên so sánh trực tiếp thời gian C với thời gian ingest A/B. Trace đầy đủ ở `starter/results/retrieval_traces.json`; số liệu tổng hợp ở `starter/results/retrieval_summary.json`.

## Audit thủ công

| Strategy | Coherence trung bình /2 (n=10) | Metadata đúng/đủ (test top-3) | Filter tuân thủ (5 câu test có filter) | Grounding 0/1/2; trung bình /2 (n=5) |
|---|---:|---:|---:|---|
| A | 1.0 | 15/15 | 5/5 quan sát được; không áp filter chủ động | 0/2/3; 1.6 |
| B | 1.1 | 15/15 | 5/5 quan sát được; không áp filter chủ động | 0/1/4; 1.8 |
| C | 1.1 | 15/15 | 5/5, filter được áp trong truy vấn | 0/1/4; 1.8 |

Mẫu coherence là chunk ordinal 0 trên 10 trang PDF đầu; C có chunk giống B. Grounding chấm khả năng top-3 cung cấp bằng chứng có thể truy nguồn. Nhãn và lý do từng mẫu nằm trong `starter/results/manual_audit.md`. Các nhãn thủ công hiện do trợ lý rà soát, chưa phải đánh giá độc lập của học viên; mẫu coherence được chọn sau khi chạy nên có tính mô tả, không phải mẫu đã đăng ký trước.

## Phân tích và kết luận

- **A so với B:** B tạo ít hơn 186 chunk (221 so với 407), giữ đoạn văn liền mạch hơn trong mẫu coherence và có Evidence Hit@3 cao hơn một câu ở cả dev (11/15 so với 10/15) lẫn test (4/5 so với 3/5). Hit@1 không đổi trên dev (9/15) nhưng tăng từ 3/5 lên 4/5 trên test. Với corpus và benchmark nhỏ này, B là lựa chọn cân bằng hơn.
- **B so với C:** C giữ nguyên kết quả retrieval tổng thể của B. Trên cả sáu câu có filter, top-3 của B vốn đã ở đúng chapter nên filter không đổi các page ID; C vẫn chứng minh filter được áp đúng và 18/18 chunk top-3 ở các truy vấn có filter tuân thủ giá trị chapter. Filter hiện ở mức chương nên còn thô.
- **Ví dụ lỗi:** q18 hỏi về kết quả nghiên cứu lựa chọn thông tin; ở A, phần bằng chứng bị cắt qua ranh giới fixed chunk nên không đạt evidence match tự động, trong khi B/C đạt. q19 hỏi lời khuyên về learning styles; top-3 có nội dung liên quan ở PDF pages 42–43 nhưng không chunk nào chứa đủ toàn bộ gold quote, nên cả ba cấu hình không đạt Evidence Hit@3.
- **Giới hạn và bước tiếp theo:** test chỉ có 5 câu và corpus là một trích đoạn của một sách; không khái quát ra corpus khác. Một số ký tự PDF bị lỗi khi trích xuất. API token và chi phí không được lưu, nên không ước đoán chi phí. Nếu làm lại, cần chốt tiêu chí chọn trên dev trước khi mở test, chọn mẫu coherence trước khi chạy, ghi usage/token từ API, và cân nhắc filter theo section nếu metadata đủ tin cậy.

## Tệp minh chứng

- Corpus manifest: `starter/data/manifest.json`
- Benchmark và gold evidence: `starter/benchmark/questions.json`
- Experiment log: `artifacts/experiment_log.csv`
- Trace và summary: `starter/results/retrieval_traces.json`, `starter/results/retrieval_summary.json`
- Nhãn audit và giới hạn: `starter/results/manual_audit.md`
