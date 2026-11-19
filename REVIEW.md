# Review code theo PLAN.md

Nguồn đối chiếu: `F:/BTL_MMT_detai/PLAN.md`. Phạm vi lần sửa này là mã mô phỏng, cấu hình, kiểm thử, thí nghiệm và phân tích dữ liệu trong `BTL_MMT`.

## Các vấn đề đã xử lý

| Vấn đề trước review | Ảnh hưởng | Thay đổi |
| --- | --- | --- |
| Phân tích tìm mọi file scalar bằng glob, không kiểm tra manifest | Có thể trộn dữ liệu cũ, thiếu run hoặc khác phiên bản nguồn vào báo cáo | Chỉ đọc run được liệt kê trong manifest hoàn tất; kiểm tra mã băm nguồn, executable, file kết quả và metadata |
| Không gắn executable với nguồn đã build | Có thể sửa C++ nhưng chạy executable cũ rồi ghi mã băm nguồn mới | Build thành công ghi `build-info.json`; runner và phân tích kiểm tra lại fingerprint |
| Số run được ghi cứng mà không đối chiếu cấu hình thực | Sửa ini có thể khiến thí nghiệm chạy thiếu hoặc sai run | Truy vấn danh sách run từ OMNeT++ và đối chiếu ma trận đã chốt |
| Kiểm thử và nghiên cứu dùng chung thư mục kết quả | Các run kiểm thử ngắn có thể bị nhầm với dữ liệu nghiên cứu | Kiểm thử ghi vào `results/tests`, thí nghiệm ghi vào `results/verified` |
| BEB chỉ được kiểm tra bằng cận chung 1023 | Chưa chứng minh cận theo giai đoạn va chạm và giới hạn cấu hình | Ghi `backoffExponent` cùng `backoffSlots`; kiểm tra từng lần rút và trường hợp cap 0/2 |
| Thiếu kiểm thử va chạm ALOHA, truyền lại Slotted và biên warmup | Dễ bỏ sót lỗi cơ chế hoặc thứ tự sự kiện tại cùng thời điểm | Thêm các cấu hình kiểm thử tất định tương ứng |
| Tham số có thể tạo thời lượng bị làm tròn về 0 hoặc bus không có nút | Khe Slotted không hợp lệ hoặc mạng rỗng vẫn chạy | Từ chối tham số không hữu hạn, thời lượng không dương ở độ phân giải hiện hành và bus không có nút |
| Kết thúc trước warmup chưa có snapshot đầu kỳ | Đối soát tồn kho không còn đúng với cửa sổ đo rỗng | Ghi hai biên bằng tồn cuối kỳ, thời gian đo bằng 0; phân tích từ chối cửa sổ đo rỗng |
| Phân tích chưa trình bày so sánh 20s với 100s | Chưa thực hiện phần kiểm tra độ ổn định trong plan | Tổng hợp và vẽ riêng kết quả Stability cùng ba mức tải tương ứng |
| Cấu hình `.anf` đọc đường dẫn kết quả cũ | OMNeT++ IDE có thể hiển thị dữ liệu chưa xác minh | Chuyển sang `results/verified/CsmaCd-*` |
| ALOHA từng xác định va chạm theo khoảng phát tại nguồn, khác bus có trễ của CSMA/CD | Chưa thống nhất môi trường truyền để so sánh các MAC | Dùng chung bus phiên bản 2, xét cả phần đuôi tín hiệu; cùng phản hồi cuối khung và guard Slotted có tính vào thời gian mô phỏng |

## Đối chiếu thiết kế

- Giữ mô hình CSMA/CD trên bus có trễ lan truyền, jam và BEB; chỉ nhận cấu hình CSMA/CD nhiều nút khi thời gian khung lớn hơn hai lần trễ lan truyền cực đại. Cả ba MAC dùng quy tắc chồng lấn tín hiệu nửa kín trên cùng bus, kể cả khi nguồn đã dừng phát.
- Giữ G là tải gói mới toàn mạng. RNG tạo gói và RNG backoff tách nhau; ba giao thức dùng cùng N, bitrate, kích thước khung, hàng đợi, thời lượng và seed.
- Giữ bộ đếm theo thời điểm sự kiện trong cửa sổ đo; kiểm tra `initialPending + generated - blocked = success + dropped + finalPending` cho từng nút.
- Giữ 345 run: CsmaCd 45, Aloha 45, Slotted 45, StudyN 60, StudyA 75, StudyBEB 60, Stability 15; tổng cộng 69 bộ tham số, mỗi bộ 5 seed.
- Báo cáo số gói thành công, thông lượng chuẩn hóa và bit/s, tỷ lệ va chạm, độ trễ, truyền lại và tỷ số chặn/loại; thanh sai số là độ lệch chuẩn mẫu giữa các seed.
- Không dùng `ketqua.csv` hay áp đường lý thuyết ALOHA trực tiếp theo G gói mới có hàng đợi và truyền lại.

## Môi trường truyền chung phiên bản 2

`Bus.cc` dùng cùng một quy tắc cho mọi MAC: hai khoảng phát tại nguồn `[si,ei)`, `[sj,ej)` làm hỏng cả hai lần thử nếu `si < ej+dij` và `sj < ei+dij`, trong đó `dij` là trễ giữa hai nút. Đây là mô hình miền va chạm broadcast bảo thủ: chồng lấn ở bất kỳ vị trí nào trên bus đều làm hỏng cả hai khung. Không mô phỏng đầu thu đích, capture effect, lỗi bit hay đầy đủ PHY IEEE.

Sau END tại e, bus giữ bản ghi đến `e+maxPropDelay` để không tuyên bố thành công trước khi biết va chạm do phần đuôi tín hiệu. Mọi MAC đều chờ phản hồi oracle chung này; delay và FIFO tính cả thời gian chờ. CSMA/CD vẫn giải quyết va chạm tại lúc phát hiện cục bộ rồi phát jam/BEB; mã lần thử giúp bỏ qua phản hồi cũ đến muộn.

Slotted ALOHA dùng khe `frameTime+maxPropDelay`, có guard để tín hiệu ở hai khe kế tiếp không chồng nhau. Tại cấu hình chính Tf=1ms, trễ cực đại 5us, chu kỳ khe là 1.005ms. Thông lượng S vẫn tính theo Tf nên chi phí guard được tính vào kết quả. CSMA/CD, Pure ALOHA và Slotted khác nhau ở cơ chế MAC; cùng topology, trễ, tiêu chí mất khung, phản hồi cuối khung, lưu lượng mới và tham số đo.

`scripts/run.py` kiểm tra scalar phiên bản vật lý 2 và tính nhất quán của chu kỳ khe. `scripts/analyze.py` kiểm tra cùng dải G/seed, tham số điều khiển và lưu lượng mới trước khi so sánh, rồi ghi phiên bản vật lý/thời gian chờ kết quả/chu kỳ khe vào CSV.

### Kiểm thử phân biệt mô hình mới với mô hình cũ

| Kịch bản | Kết quả đã kiểm tra |
| --- | --- |
| Hai gói sinh tại 1ms và 2.002ms, Tf=1ms, trễ 5us, Pure ALOHA | Cả hai hỏng dù khoảng phát tại nguồn không chồng nhau |
| Cùng thời điểm sinh nhưng trễ 0 | Cả hai thành công |
| Nút thứ hai phát đúng tại 2.005ms | Cả hai thành công, xác nhận biên nửa kín |
| Cùng thời điểm sinh 1ms/2.002ms với CSMA/CD | Cảm nhận tín hiệu còn trên bus, chờ kênh và thành công cả hai |
| Ba nút, cặp nút gần nhau cách 2.5us; gói sau sinh tại 2.003ms | Cả hai thành công; kiểm tra trễ theo khoảng cách, không dùng cận 5us cho mọi cặp |
| Trễ 400us, hai nguồn ALOHA phát cách nhau 1.2ms | Cả hai hỏng do phần đuôi tín hiệu |
| Trễ 400us, Slotted có guard | Hai khe kế tiếp thành công |
| Kết thúc khi khung chờ kết quả hoặc jam còn phản hồi đang bay | Gói được đối soát đúng, không ghi thành công sớm |

### Đối chiếu kết quả trước và sau sửa

Bản cũ được lưu tại `results/archive/before-common-phy.zip`, gồm nguồn, executable, manifest, dữ liệu và biểu đồ. Bảng dưới lấy S trung bình từ summary của hai phiên bản, cùng 5 seed.

| G | MAC | S trước | S sau, bus chung |
| --- | --- | --- | --- |
| 0.6 | CSMA/CD | 0.598589 | 0.598656 |
| 0.6 | Pure ALOHA | 0.055533 | 0.055567 |
| 0.6 | Slotted ALOHA | 0.298322 | 0.297467 |
| 1.5 | CSMA/CD | 0.891911 | 0.925433 |
| 1.5 | Pure ALOHA | 0.055556 | 0.055811 |
| 1.5 | Slotted ALOHA | 0.297611 | 0.296633 |

Đây là tác động tổng hợp của phiên bản mới, gồm quy tắc phần đuôi tín hiệu, thời gian chờ kết quả chung và guard Slotted. Không quy riêng mọi thay đổi thông lượng cho trễ lan truyền. Thứ hạng quan sát tại các mức tải này vẫn là CSMA/CD, Slotted ALOHA, Pure ALOHA; kết luận chỉ áp dụng cho mô hình và cơ chế backoff đã công bố.

## Kiểm chứng

Ngày 14/11/2026: build release thành công, **32/32 kiểm thử tích hợp** và **14/14 kiểm thử workflow** đạt. Ngoài cơ chế MAC và biên lan truyền, workflow kiểm tra việc từ chối nguồn/executable/kết quả bị thay đổi, run thiếu hoặc trùng, metadata sai, seed trùng, tổng hợp metric không xác định và phép so sánh khác điều kiện vật lý/lưu lượng.

Đã chạy lại **345/345 run** với bus chung phiên bản 2, tổng hợp **69 bộ tham số**, mỗi bộ đủ **5 seed**, và xuất **10 biểu đồ**. Manifest có trạng thái `complete`; tất cả metric trong bộ dữ liệu này có đủ 5 seed hợp lệ. Kiểm tra trực quan biểu đồ so sánh thông lượng và khảo sát trễ cho thấy nhãn, đơn vị, chú giải và thanh sai số hiển thị đầy đủ.

| G | S trung bình, run 20s / warmup 2s | S trung bình, run 100s / warmup 10s | Thay đổi tương đối |
| --- | --- | --- | --- |
| 0.1 | 0.099822 | 0.099700 | -0.1224% |
| 0.6 | 0.598656 | 0.602829 | +0.6971% |
| 1.5 | 0.925433 | 0.923458 | -0.2135% |

Các chỉ tiêu độ trễ, va chạm và chặn/loại của phép kiểm tra thời lượng được lưu cùng trong `results/summary/stability.csv`.

Lệnh tái lập:

```powershell
./scripts/build.ps1
python scripts/run.py test
python -m unittest discover -s scripts -p test_workflow.py -v
python scripts/run.py experiments
python scripts/analyze.py
```

Kết quả kiểm thử nằm trong `results/tests/tests.json`; dữ liệu thí nghiệm và fingerprint nằm trong `results/verified/manifest.json`. `results/summary/runs.csv` và `summary.csv` được dựng từ scalar đã kiểm tra, không từ CSV cũ.

## Phần còn lại của bài nộp

Hoàn tất code và dữ liệu không đồng nghĩa hoàn tất mọi sản phẩm của PLAN.md. Báo cáo PDF 15–25 trang, slide bảo vệ, video 3–5 phút hoặc minh chứng được chấp nhận, tên/MSSV của 5 thành viên, nhật ký đóng góp thực tế, xác nhận phạm vi và gói ZIP nộp bài vẫn cần chuẩn bị riêng. Không tự gán đóng góp hay phê duyệt giảng viên.
