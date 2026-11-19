# Kịch bản trình diễn 3–5 phút

## 0:00–0:40 Mô hình

Mở `CsmaCd.ned`, chỉ bus và các nút; giải thích Ethernet chia sẻ bán song công, nguồn Poisson và FIFO. Cả ba MAC dùng cùng trễ theo khoảng cách, quy tắc chồng lấn tín hiệu trên bus và thời điểm nhận kết quả cuối khung. Slotted có guard bằng trễ cực đại; phản hồi là oracle chung, chưa hiện thực ACK.

## 0:40–1:40 Kiểm chứng cơ chế

Chạy `python scripts/run.py test`. Mở log TestCollision, TestWait và TestDrop trong `results/tests`. Đối chiếu scalar va chạm, backoff, chờ kênh, thành công và loại gói. Mở vector BEB để kiểm tra từng giá trị K theo số mũ của lần backoff tương ứng. Có thể mở Qtenv bằng executable rồi chọn TestCollision để quan sát sự kiện.

Đối chiếu `TestPropagationTail` với `TestCsmaPropagationTail`: hai gói đến tại 1ms và 2.002ms, thời gian khung 1ms, trễ 5us. ALOHA làm hỏng cả hai do tín hiệu còn trên bus, còn CSMA/CD chờ kênh rồi truyền thành công. `TestNoPropagationTail` dùng cùng thời điểm sinh gói nhưng trễ 0 và thành công; `TestPropagationBoundary` xác nhận tại đúng 2.005ms không còn va chạm. `TestSlottedLongPropagation` kiểm tra guard với trễ lớn 400us.

## 1:40–2:40 Kết quả

Mở các biểu đồ comparison_S, comparison_collision_ratio, StudyA; chỉ rõ tải, đơn vị, 5 seed và thanh sai số là độ lệch chuẩn.

## 2:40–3:40 Khả năng tái lập

Mở `results/verified/manifest.json`, `results/summary/runs.csv` và `results/summary/summary.csv`. Trình bày cách tính S từ scalar. Chạy `python scripts/analyze.py` để kiểm tra nguồn, tính toàn vẹn dữ liệu và dựng lại đồ thị. Chỉ biểu đồ độ ổn định để so sánh cửa sổ 20s/2s với 100s/10s.

## 3:40–4:30 Giới hạn và bảo vệ

Giải thích tải gói mới khác tải gồm truyền lại, gói tồn đầu/cuối cửa sổ, khung chờ kết quả và mô hình bus chung không có capture effect hay ACK thực. Mỗi thành viên giải thích phần việc đã thực hiện.

DOCX cho phép video hoặc minh chứng tương đương. Bộ log thật và kết quả kiểm thử chứng minh cơ chế đã chạy; nhóm cần xác nhận với giảng viên chúng đáp ứng hình thức minh chứng tương đương, hoặc quay thao tác theo kịch bản trên để có video 3–5 phút.
