# ET4230 Đề 03 — CSMA/CD

Mô phỏng Ethernet chia sẻ bán song công bằng OMNeT++ 6.4.0, so sánh CSMA/CD với Pure ALOHA và Slotted ALOHA. Mã ban đầu trong thư mục được điều chỉnh để chuẩn hóa số đo, xử lý khe thời gian và bổ sung kiểm thử. Không dùng `ketqua.csv` hoặc kết quả cũ để tạo báo cáo mới.

## Chạy lại

Trong PowerShell ở thư mục dự án, với Python 3.10+ và OMNeT++ 6.4.0 đã cài:

```powershell
./scripts/build.ps1
python scripts/run.py test
python -m unittest discover -s scripts -p test_workflow.py -v
python scripts/run.py experiments
python -m pip install matplotlib
python scripts/analyze.py
```

`build.ps1` tìm OMNeT++ hai cấp phía trên dự án (`samples/BTL_MMT`), thêm các thư mục công cụ vào PATH của tiến trình hiện tại và ghi `build-info.json` sau khi make thành công. Nếu đặt dự án ở nơi khác, chỉnh biến `OMNET` trong `scripts/run.py` và `omnetRoot` trong `scripts/build.ps1`. Khi build bằng `make MODE=release` trong shell OMNeT++ đã cấu hình, chạy thêm `python scripts/run.py record-build` ngay sau khi make thành công để ghi fingerprint trước khi dùng runner.

Chạy một nhóm: `python scripts/run.py experiments --configs CsmaCd`. Lệnh mặc định chạy 345 lần: CsmaCd 45, Aloha 45, Slotted 45, StudyN 60, StudyA 75, StudyBEB 60, Stability 15. Mỗi bộ tham số lặp 5 seed 0–4. Runner kiểm tra số run bằng truy vấn cấu hình từ executable. Manifest ghi nguồn, executable, tham số, seed, thời lượng và mã băm file kết quả; chạy lại tập con sẽ thay manifest bằng tập con đó. Để lấy toàn bộ bản bàn giao, dùng lệnh mặc định.

Phân tích chỉ đọc các run trong manifest hoàn tất và kiểm tra mã băm trước khi tổng hợp. File cũ còn nằm trong `results/` không tự động trở thành dữ liệu đã xác minh. Khi sửa nguồn hoặc cấu hình, chạy lại build, kiểm thử và thí nghiệm trước khi dựng biểu đồ. Xem `REVIEW.md` để đối chiếu các thay đổi với `F:/BTL_MMT_detai/PLAN.md`.

## Mô hình và giới hạn

- N nút nằm đều trên bus; trễ giữa i và j bằng `maxPropDelay * abs(i-j)/(N-1)`.
- G là tải **gói mới** toàn mạng, với thời gian giữa hai gói tại một nút có kỳ vọng `N*frameTime/G`. Bộ sinh gói dùng RNG 0, backoff dùng RNG 1 để tránh backoff làm thay đổi chuỗi sinh gói.
- Mỗi nút có FIFO, `queueLimit` tính cả gói đang phục vụ. Gói tràn bị chặn, gói đủ `maxAttempts` lần thử mà chưa thành công bị loại.
- CSMA/CD dùng cảm nhận sóng mang có trễ, phát jam và BEB với `K~U{0,...,2^min(attempts,maxBackoffExp)-1}`. Backoff chạy theo thời gian thực rồi cảm nhận lại kênh. Slot bằng `max(slotBits/bitrate,2*maxPropDelay)`.
- Khung CSMA/CD phải dài hơn hai lần trễ lan truyền cực đại khi có nhiều nút. Điều kiện nghiêm ngặt tránh trường hợp biên thứ tự sự kiện; không tuyên bố đây là bộ mô phỏng chuẩn IEEE đầy đủ.
- **Cả ba giao thức dùng cùng mô hình bus phiên bản 2.** Với hai lần phát tại i và j có khoảng phát tại nguồn `[si,ei)` và `[sj,ej)`, trễ `dij`, tín hiệu chồng nhau ở một vị trí trên bus khi `si < ej+dij` và `sj < ei+dij`. Khi đó cả hai lần phát hỏng. Bus giữ lịch sử phần đuôi tín hiệu, kể cả khi nút nguồn đã dừng phát; không còn oracle va chạm riêng cho ALOHA.
- Sau khi nguồn kết thúc phát tại e, **mọi giao thức** chờ đến `e+maxPropDelay` để nhận kết quả thành/bại từ bus. Đây là phản hồi oracle mô phỏng dùng chung, không hiện thực ACK hay gói tin phản hồi. Thời gian chờ này nằm trong delay và thời gian phục vụ FIFO. CSMA/CD vẫn giải quyết thất bại ngay khi cảm nhận va chạm, phát jam và BEB; kết quả đến muộn của lần thử đó được bỏ qua bằng mã lần thử.
- Slotted ALOHA dùng chu kỳ khe `frameTime+maxPropDelay`, gồm một khung và khoảng bảo vệ để phần đuôi của khe trước thoát khỏi bus. Căn khe bằng tick nguyên; tại cấu hình chính, khe là **1.005ms**, không phải 1ms. Khi trễ bằng 0, khe trở về đúng thời gian khung. Pure ALOHA truyền lại sau 1–`retxWindow` thời gian khung; Slotted ALOHA dùng 1–`retxWindow` chu kỳ khe rồi căn biên khe tiếp theo.
- Khác biệt giữa các MAC nằm ở cảm nhận kênh, dừng sớm/jam, cách chọn thời điểm phát và backoff. Điều kiện môi trường, quy tắc tín hiệu chồng lấn và phản hồi cuối khung giống nhau. Script phân tích từ chối so sánh nếu dải G/seed, tham số vật lý/hàng đợi/thời lượng hoặc số gói mới của cùng G/seed khác nhau.
- Mô hình broadcast bảo thủ: tín hiệu chồng nhau tại bất kỳ vị trí nào trên bus làm hỏng cả hai khung. Bỏ qua capture effect, IFG, preamble, địa chỉ MAC, CRC, lỗi bit, đầu thu cụ thể và giao thức tầng trên. `frameBits` là toàn bộ lượng bit mô hình, không phải payload ứng dụng. Không suy rộng thành hiệu năng Ethernet switched full-duplex hiện đại.
- Bộ sinh thử nghiệm `deterministic=true` chỉ tạo một gói tại `firstArrival`, dùng cho kiểm chứng cơ chế.
- Thời gian khung, jam và slot phải biểu diễn được ở độ phân giải thời gian mô phỏng. Tham số không hữu hạn, bus không có nút và các thời gian không hợp lệ bị từ chối.

## Quy ước số đo

Cửa sổ đo là từ warmup tới thời điểm kết thúc. Bộ đếm theo **thời điểm sự kiện**. Gói sinh trước warmup nhưng kết thúc trong cửa sổ vẫn đóng góp vào throughput và delay; độ trễ bao gồm toàn bộ thời gian từ lúc sinh. Snapshot hàng đợi đầu kỳ cho phép đối soát:

`initialPending + generated - blocked = success + dropped + finalPending`.

Nếu mô phỏng kết thúc trước warmup, cửa sổ đo rỗng: các bộ đếm bằng 0 và hai snapshot hàng đợi được ghi bằng tồn cuối kỳ. Script phân tích từ chối run có thời gian đo bằng 0.

`generated` gồm cả gói bị chặn. `txAttempts` đếm lần bắt đầu thử, `retransmissions` đếm lần bắt đầu thử thứ hai trở đi, gồm cả gói sau đó bị loại. `collisions` đếm **lần thử thất bại** theo thời điểm phát hiện/kết thúc, không đếm một sự kiện va chạm vật lý chung. `resolvedAttempts` gồm thành công và lần thử phát hiện thất bại. Các lần thử cắt qua biên thời gian có thể được tính ở các cửa sổ khác nhau.

Thành công của cả ba MAC được ghi khi nhận kết quả từ bus; thất bại ALOHA cũng được ghi tại thời điểm này. Thất bại CSMA/CD được ghi khi phát hiện va chạm cục bộ. Khung đã phát hết nhưng còn đợi kết quả vẫn thuộc `finalPending`. Scalar ghi thêm `phyModelVersion=2`, `propagationTime` và `alohaSlotTime`; CSV ghi các cột tương ứng `phy_model_version`, `settlement_time_s`, `slotted_period_s` (chu kỳ dành cho Slotted, không phải slot BEB của CSMA/CD).

Với T là thời gian đo, B là frameBits và Tf là frameTime:

| Chỉ tiêu | Công thức toàn mạng |
| --- | --- |
| Thông lượng chuẩn hóa S | sum(success) * Tf / T |
| Thông lượng bit/s | sum(success) * B / T |
| Tải thử truyền quan sát | sum(txAttempts) * Tf / T |
| Tải gói mới quan sát | sum(generated) * Tf / T |
| Tỷ lệ va chạm | sum(collisions) / sum(resolvedAttempts) |
| Độ trễ trung bình, s | sum(delaySum) / sum(success) |
| Tỷ phần truyền lại | sum(retransmissions) / sum(txAttempts) |
| Tỷ số loại/chặn | (sum(blocked)+sum(dropped)) / sum(generated) |

Tỷ số loại/chặn là tỷ số sự kiện trong cửa sổ, không phải xác suất mất của cùng một cohort gói. Gói còn chờ cuối kỳ chưa được kết luận mất. Đồ thị thể hiện trung bình và **độ lệch chuẩn mẫu** giữa 5 seed, không phải khoảng tin cậy. Delay được gộp theo số gói thành công trong từng run trước khi lấy trung bình giữa run.

Nếu một seed không có gói thành công thì delay của seed đó là `NaN`, không phải 0. Tương tự, tỷ số có mẫu số bằng 0 được để `NaN`. Các cột `*_valid_runs` trong summary ghi rõ số seed có giá trị xác định được dùng để tính trung bình và độ lệch chuẩn.

Không vẽ `G*exp(-2G)` hoặc `G*exp(-G)` trực tiếp theo G gói mới: hệ thống có hàng đợi, backoff và truyền lại nên không đáp ứng giả định tải thử Poisson độc lập lý tưởng.

## Dữ liệu và hồ sơ

- `results/verified/`: scalar `.sca`, log từng lần chạy thí nghiệm và manifest.json.
- `results/tests/`: scalar, vector, log kiểm thử cơ chế và tests.json; tách khỏi dữ liệu nghiên cứu.
- `results/summary/`: runs.csv và summary.csv; script chỉ đọc dữ liệu mới của các cấu hình nghiên cứu.
- `results/summary/stability.csv`: đối chiếu trung bình và độ lệch chuẩn giữa run 20s/2s warmup và 100s/10s warmup tại G=0.1, 0.6, 1.5.
- `results/archive/before-common-phy.zip`: bản lưu nguồn, executable, manifest, dữ liệu và biểu đồ trước khi chuẩn hóa bus; chỉ dùng đối chiếu lịch sử, không trộn với dữ liệu phiên bản 2.
- `plots/`: biểu đồ tái dựng từ scalar.
- `report/`: hiện có mẫu phân công và nhật ký đóng góp; báo cáo PDF 15–25 trang còn phải thực hiện.
- `demo/`: kịch bản trình diễn 3–5 phút; log kiểm thử là bằng chứng cơ chế, cần xác nhận hình thức minh chứng được chấp nhận khi nộp.
- Slide bảo vệ, video hoặc bộ minh chứng được chấp nhận và gói ZIP nộp bài còn phải chuẩn bị riêng.

Mã nguồn NED/C++ giữ ở gốc để tương thích dự án OMNeT++ hiện có. Mã băm nguồn trong manifest phải khớp nguồn trước khi tái sử dụng số liệu. Các mẫu phân công không chứng minh đóng góp thực tế.

## Tài liệu và AI

- Đề bài ET4230 bản cập nhật 10/2026 trong `F:/BTL_MMT_detai`.
- [OMNeT++ Simulation Manual](https://doc.omnetpp.org/omnetpp/manual/): sự kiện, scheduling priority, seed-set và warmup.
- [IEEE 802.3-2018](https://standards.ieee.org/ieee/802.3/7071/): phạm vi Ethernet half/full-duplex. Mô hình không hiện thực toàn bộ chuẩn.

AI hỗ trợ rà soát/sửa mã, tạo script kiểm thử, chạy thí nghiệm và soạn tài liệu. Nhóm cần đọc, kiểm chứng và bảo vệ toàn bộ nội dung. Không có tên, đóng góp hoặc phê duyệt giảng viên nào được tự gán.
