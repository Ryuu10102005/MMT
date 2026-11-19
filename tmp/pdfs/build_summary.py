from pathlib import Path
import ast
import csv
import hashlib
import io
import json
import sys
sys.stdout.reconfigure(encoding='utf-8')
from xml.sax.saxutils import escape
import zipfile

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak,
)
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/pdf/BTL_MMT_Tong_hop_cong_viec_va_ket_qua.pdf'
OUT.parent.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / 'scripts'))
from run import provenance, read_sca, totals

manifest = json.loads((ROOT/'results/verified/manifest.json').read_text(encoding='utf-8'))
tests = json.loads((ROOT/'results/tests/tests.json').read_text(encoding='utf-8'))
current = provenance()
assert manifest['status'] == 'complete' and len(manifest['runs']) == 345
assert all(manifest[k] == v and tests[k] == v for k, v in current.items())
summary = list(csv.DictReader((ROOT/'results/summary/summary.csv').open(encoding='utf-8')))
stability = list(csv.DictReader((ROOT/'results/summary/stability.csv').open(encoding='utf-8')))
assert len(summary) == 69 and len(tests['passed']) == 32
assert all(r['runs'] == '5' and r['phy_model_version'] == '2.0' for r in summary)
assert all(r[k] == '5' for r in summary for k in r if k.endswith('_valid_runs'))
unit_names = [n.name for n in ast.walk(ast.parse((ROOT/'scripts/test_workflow.py').read_text(encoding='utf-8')))
              if isinstance(n, ast.FunctionDef) and n.name.startswith('test_')]
assert len(unit_names) == 14

for name, filename in [('Arial', 'arial.ttf'), ('Arial-Bold', 'arialbd.ttf'),
                       ('Arial-Italic', 'ariali.ttf'), ('Arial-BoldItalic', 'arialbi.ttf')]:
    pdfmetrics.registerFont(TTFont(name, str(Path('C:/Windows/Fonts')/filename)))
pdfmetrics.registerFontFamily('Arial', normal='Arial', bold='Arial-Bold',
                              italic='Arial-Italic', boldItalic='Arial-BoldItalic')

PAGE_W, PAGE_H = A4
MARGIN = 18*mm
WIDTH = PAGE_W - 2*MARGIN
STORY = []
STYLES = {
    'body': ParagraphStyle('Body', fontName='Arial', fontSize=10.4, leading=15.1, spaceAfter=7.5),
    'small': ParagraphStyle('Small', fontName='Arial', fontSize=9.1, leading=12.8, spaceAfter=6),
    'caption': ParagraphStyle('Caption', fontName='Arial-Italic', fontSize=8.8, leading=12.3,
                              textColor=colors.HexColor('#4b5563'), spaceBefore=3, spaceAfter=9),
    'h1': ParagraphStyle('H1', fontName='Arial-Bold', fontSize=18, leading=24, spaceAfter=12),
    'cover': ParagraphStyle('Cover', fontName='Arial-Bold', fontSize=25, leading=32, spaceAfter=14),
    'h2': ParagraphStyle('H2', fontName='Arial-Bold', fontSize=11.7, leading=16, spaceBefore=9,
                         spaceAfter=7, keepWithNext=True),
    'cell': ParagraphStyle('Cell', fontName='Arial', fontSize=9.2, leading=12.6),
    'head': ParagraphStyle('Head', fontName='Arial-Bold', fontSize=9.2, leading=12.6),
    'code': ParagraphStyle('Code', fontName='Arial', fontSize=9.2, leading=14.1, spaceAfter=4),
}

class SectionTitle(Paragraph):
    def __init__(self, title, key, cover=False):
        super().__init__(escape(title), STYLES['cover' if cover else 'h1'])
        self.section_title, self.section_key = title, key

class SummaryDoc(SimpleDocTemplate):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sections = []
    def afterFlowable(self, flowable):
        if isinstance(flowable, SectionTitle):
            self.canv.bookmarkPage(flowable.section_key)
            self.canv.addOutlineEntry(flowable.section_title, flowable.section_key, level=0, closed=False)
            self.sections.append({'page': self.page, 'title': flowable.section_title})

def para(text, style='body'):
    STORY.append(Paragraph(escape(str(text)).replace('\n', '<br/>'), STYLES[style]))

def h2(text):
    para(text, 'h2')

def section(title, cover=False):
    if STORY:
        STORY.append(PageBreak())
    STORY.append(SectionTitle(title, 'section-'+str(sum(isinstance(x, SectionTitle) for x in STORY)+1), cover))

def bullet(text):
    para('• '+text)

def table(headers, rows, widths, size=9.2, padding=5):
    cs = ParagraphStyle('CellLocal', parent=STYLES['cell'], fontSize=size, leading=size*1.36)
    hs = ParagraphStyle('HeadLocal', parent=STYLES['head'], fontSize=size, leading=size*1.36)
    data = [[Paragraph(escape(str(c)), hs) for c in headers]]
    data += [[Paragraph(escape(str(c)).replace('\n','<br/>'), cs) for c in row] for row in rows]
    t = Table(data, colWidths=[WIDTH*x/sum(widths) for x in widths], repeatRows=1, hAlign='LEFT')
    t.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eef1f4')),
        ('GRID',(0,0),(-1,-1),.45,colors.HexColor('#d9d9d9')),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),
        ('TOPPADDING',(0,0),(-1,-1),padding),('BOTTOMPADDING',(0,0),(-1,-1),padding),
    ]))
    STORY.extend([t,Spacer(1,8)])

def plot(filename, caption, width=None):
    w = width or WIDTH
    STORY.append(Image(str(ROOT/'plots'/filename), width=w, height=w*675/1200))
    para(caption, 'caption')

def fmt(value, digits=6):
    return f'{float(value):.{digits}f}'.replace('.', ',')

def find(config, g):
    return next(r for r in summary if r['config']==config and float(r['G'])==g)

def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont('Arial',8)
    canvas.setFillColor(colors.HexColor('#56616b'))
    canvas.drawString(MARGIN,PAGE_H-10*mm,'BTL MMT  |  ET4230  |  Đề 03 CSMA/CD')
    canvas.drawRightString(PAGE_W-MARGIN,PAGE_H-10*mm,'Tổng hợp ngày 18/11/2026')
    canvas.setStrokeColor(colors.HexColor('#d9d9d9'))
    canvas.setLineWidth(.5)
    canvas.line(MARGIN,PAGE_H-13*mm,PAGE_W-MARGIN,PAGE_H-13*mm)
    canvas.drawString(MARGIN,9*mm,'Mô hình bus chung phiên bản 2')
    canvas.drawRightString(PAGE_W-MARGIN,9*mm,f'Trang {doc.page}')
    canvas.restoreState()

# 1
section('Tổng hợp công việc và kết quả mô phỏng CSMA/CD', cover=True)
para('Học phần Mạng máy tính ET4230 | Đề 03 | Dự án BTL_MMT', 'h2')
para('Tài liệu ghi lại các phần đã rà soát, sửa và bổ sung trên dự án có sẵn: mô hình, cơ chế MAC, kiểm thử, thiết kế thí nghiệm, dữ liệu, biểu đồ, demo và công việc còn lại.')
table(['Lượt thí nghiệm','Bộ tham số','Kiểm thử đã đạt','Biểu đồ'],
      [['345','69 × 5 seed','32 tích hợp + 14 workflow','10']], [1,1,1.3,1],size=10,padding=12)
para('Phần kỹ thuật đã có bộ chạy và dữ liệu theo plan. Mã nguồn, executable và dữ liệu được gắn bằng fingerprint; bản tổng hợp trước đó đã tính lại 69 nhóm từ 345 run thô và đối chiếu khớp CSV.')
para('Bản PDF này là tổng hợp công việc và bằng chứng kỹ thuật để theo dõi tiến độ, học và chuẩn bị bảo vệ. Đây chưa phải báo cáo nộp chính thức có đầy đủ thông tin nhóm, lý thuyết và hồ sơ đóng góp.', 'small')
h2('Nội dung tra cứu')
table(['Trang','Nội dung'],[
    ['2','Đối chiếu yêu cầu và phạm vi đã hoàn thành'],
    ['3-5','Thông số, sinh gói, CSMA/CD và môi trường truyền chung'],
    ['6-7','Bộ đếm, warmup, công thức và cách tổng hợp'],
    ['8-9','32 kiểm thử tích hợp và 14 kiểm thử workflow'],
    ['10','Ma trận 7 nhóm thí nghiệm và 345 lượt chạy'],
    ['11-14','Kết quả so sánh, khảo sát N, a, BEB và độ ổn định'],
    ['15','Demo thực tế và timeline va chạm'],
    ['16-18','File bàn giao, dữ liệu, giới hạn và việc còn thiếu'],
    ['19-21','Phụ lục các biểu đồ còn lại'],
], [1,6],padding=4)
para('Nguồn chính: PLAN.md, README.md, REVIEW.md, omnetpp.ini, tests.json, manifest.json và các CSV trong results/summary. Số liệu chính là trung bình 5 seed của bus phiên bản 2, trừ các ví dụ được ghi riêng là seed 0.', 'caption')

# 2
section('Đối chiếu yêu cầu và phạm vi')
para('CSMA/CD là đối tượng chính. Pure ALOHA và Slotted ALOHA là hai baseline để so sánh định lượng trong cùng điều kiện được công bố. Phạm vi là Ethernet lịch sử dùng chung đường truyền, bán song công.')
table(['Yêu cầu','Phần đã thực hiện'],[
 ['Mô phỏng cơ chế CSMA/CD','Cảm nhận kênh có trễ, phát hiện va chạm, hủy khung, jam và binary exponential backoff.'],
 ['So sánh với ALOHA','Cả Pure ALOHA và Slotted ALOHA dùng cùng bus, trễ theo vị trí, quy tắc va chạm và phản hồi cuối khung.'],
 ['Ít nhất 3 kịch bản','Tải nhẹ G=0,1; trung bình G=0,6; cao G=1,5, cùng dải G mở rộng.'],
 ['Ít nhất 2 tham số khảo sát','Đã khảo sát tải G, số nút N, tỷ lệ trễ a và giới hạn số mũ BEB.'],
 ['Đo hiệu năng','Thông lượng, va chạm, độ trễ, số lần truyền lại; bổ sung chặn/loại và tồn kho gói.'],
 ['Lặp ngẫu nhiên','5 seed 0-4 cho mỗi bộ tham số; tổng hợp trung bình và độ lệch chuẩn mẫu.'],
 ['Kiểm thử cơ chế','32 kiểm thử tích hợp đạt, bao phủ hành vi cơ bản và các biên lan truyền, warmup, hàng đợi.'],
 ['Dữ liệu có thể chạy lại','Script build/chạy/phân tích; raw scalar/log, manifest, CSV và 10 biểu đồ.'],
 ['Giải thích giới hạn','Đã ghi oracle chung, không ACK thực, mô hình broadcast bảo thủ và các phần PHY bị bỏ qua.'],
 ['Hồ sơ nhóm và bảo vệ','Có mẫu phân công và kịch bản demo; tên/MSSV, đóng góp thực tế và hồ sơ cuối cùng còn thiếu.'],
], [2.15,5],padding=6)
h2('Cách hiểu mức độ hoàn thành')
para('Đã hoàn thành bộ code và thí nghiệm trong phạm vi mô hình đã chọn; không tự coi đó là xác nhận giảng viên phê duyệt hay hoàn tất toàn bộ bài nộp. Báo cáo chính thức, slide, bộ minh chứng demo được biên tập, hồ sơ nhóm và gói nộp vẫn cần hoàn thiện.')
para('Đề gốc khuyến nghị báo cáo 15-25 trang và lặp ngẫu nhiên từ 5 lần; plan của dự án đã chọn cụ thể 5 seed cho mỗi bộ tham số. Tài liệu này không tự gán tên, MSSV hay đóng góp cá nhân.', 'small')

# 3
section('Mô hình nền và cấu hình cơ sở')
para('Node sinh gói, giữ FIFO, thực hiện giao thức và ghi thống kê. Bus chuyển START/END theo khoảng cách và trả kết quả truyền. CsmaCd.ned khai báo topology, tham số, signal và statistic; omnetpp.ini định nghĩa thí nghiệm.')
table(['Thông số','Giá trị cơ sở','Ý nghĩa'],[
 ['N','10','Số nút trong so sánh ba MAC'],['Bitrate R','10 Mbps','Tốc độ đường truyền mô hình'],
 ['Frame B','10.000 bit','Toàn bộ bit của khung mô hình'],['Frame time Tf','1 ms','Tf = B/R'],
 ['Trễ cực đại τ','5 µs','Trễ giữa hai đầu bus'],['Jam','32 bit = 3,2 µs','Sau khi phát hiện va chạm'],
 ['slotBits','512 bit','Dùng tính slot BEB'],['Slot BEB','51,2 µs','max(512/R, 2τ)'],
 ['maxAttempts','16','Gồm lần thử đầu tiên'],['maxBackoffExp','10','Cận số mũ BEB'],
 ['queueLimit','10 gói/nút','Gồm gói đang phục vụ'],['retxWindow','10','Chờ ngẫu nhiên 1-10 đơn vị'],
 ['Khe Slotted','1,005 ms','Tf + τ, có khoảng bảo vệ'],
], [2,1.75,3.25],padding=4)
h2('Topology và trễ')
para('Các nút nằm đều trên bus. Với N>1: d(i,j) = τ × |i-j|/(N-1). Một nút đơn lẻ không có tín hiệu từ nút khác. Mọi MAC dùng cùng topology và trễ này.')
h2('Sinh gói và hàng đợi')
para('G là tải gói mới toàn mạng. Tốc độ đến kỳ vọng λ = G/Tf; khoảng sinh gói trung bình mỗi nút E[IAT] = N×Tf/G. Khoảng đến được lấy theo phân bố mũ. RNG sinh gói tách khỏi RNG backoff.')
table(['G','Gói mới/s toàn mạng','E[IAT] mỗi nút với N=10'],[
 ['0,1','100','100 ms'],['0,6','600','16,667 ms'],['1,5','1.500','6,667 ms'],
], [1,2,3],padding=4)
para('FIFO phục vụ gói vào trước. Đầy hàng đợi thì blocked; hết lượt thử thì dropped. Chế độ deterministic chỉ sinh một gói/nút tại firstArrival để kiểm tra hành vi có thể dự đoán.', 'small')

# 4
section('CSMA/CD và binary exponential backoff')
steps=[
 'Gói đầu FIFO được đưa vào phục vụ; số lần thử của gói được khởi tạo.',
 'Nút kiểm tra tín hiệu đang nhận tại vị trí của mình. Kênh bận thì chờ END.',
 'Kênh rỗi thì phát START, tăng txAttempts và lên lịch kết thúc sau Tf.',
 'Tín hiệu nút khác đến khi đang phát làm nút phát hiện va chạm.',
 'Hủy txEnd của khung, tăng collisions/resolvedAttempts trong cửa sổ đo và phát jam.',
 'Hết jam thì gửi END. Nếu đã đủ maxAttempts, loại gói; nếu chưa, thực hiện BEB.',
 'Chọn số nguyên K trong cửa sổ hiện hành, chờ K×slotTime rồi cảm nhận lại kênh.',
 'Nếu phát hết khung không va chạm, chờ phản hồi bus trước khi ghi thành công.',
 'Ghi delay từ lúc sinh tới lúc nhận kết quả, lấy gói ra khỏi FIFO và phục vụ gói kế tiếp.',
]
for i,s in enumerate(steps,1):para(f'{i}. {s}')
h2('Công thức và cận BEB')
para('n = min(attempts, maxBackoffExp)\nK được chọn đều trong {0, ..., 2^n - 1}\nTbackoff = K × max(slotBits/R, 2τ)')
table(['Sau lần thất bại','Cửa sổ K khi chưa chạm cap'],[
 ['1','0-1'],['2','0-3'],['3','0-7'],['Từ số mũ 10','0-1023 khi cap=10'],
], [2,4],padding=4)
para('Vector backoffSlots và backoffExponent cho phép đối chiếu từng lần rút. Backoff trong mô hình chạy theo thời gian thực; khi hết thời gian, nút cảm nhận lại và tiếp tục chờ nếu kênh còn bận.')
h2('Kiểm tra cấu hình')
para('Nhiều nút CSMA/CD yêu cầu Tf > 2τ. Code từ chối G/bitrate không hữu hạn hoặc không dương, thời lượng bị làm tròn về 0, firstArrival sai, queue/retry/backoff không hợp lệ và mạng không có nút. Đây là mô hình giản lược, không phải bộ hiện thực đầy đủ IEEE 802.3.', 'small')

# 5
section('Môi trường truyền chung cho ba MAC')
para('Bản ban đầu xét ALOHA theo khoảng phát tại nguồn, còn CSMA/CD dùng cảm nhận kênh có trễ. Đã chuẩn hóa thành bus phiên bản 2 để thống nhất môi trường của phép so sánh.')
h2('Quy tắc va chạm chung')
para('Với các khoảng phát tại nguồn [si,ei), [sj,ej) và trễ dij, cả hai lần thử hỏng khi:\nsi < ej+dij và sj < ei+dij.\nMô hình broadcast bảo thủ coi chồng lấn ở bất kỳ vị trí nào trên bus là va chạm. Bus giữ lịch sử phần đuôi tín hiệu sau END.')
table(['MAC','Điểm khác nhau ở cơ chế truy nhập'],[
 ['CSMA/CD','Nghe kênh trước khi phát; phát hiện va chạm để dừng sớm, jam và BEB.'],
 ['Pure ALOHA','Có gói thì phát ngay; phát hết khung rồi nhận kết quả; chờ ngẫu nhiên 1-10 Tf khi thất bại.'],
 ['Slotted ALOHA','Chỉ phát tại biên khe; chờ 1-10 chu kỳ khe rồi căn biên khi truyền lại.'],
], [1.5,5.5],padding=7)
h2('Phản hồi và guard')
para('Sau khi nguồn kết thúc tại e, mọi MAC đợi đến e+τ để nhận kết quả từ bus. Đây là oracle mô phỏng chung, không phải gói ACK. Khung đang chờ vẫn thuộc hàng đợi; thời gian chờ được tính vào delay. Phản hồi cũ sau jam được bỏ qua bằng mã lần thử.')
para('Slotted dùng chu kỳ Tf+τ để hai khe kế tiếp không chồng phần đuôi tín hiệu. Căn khe bằng tick nguyên; S vẫn chuẩn hóa theo Tf nên chi phí guard được phản ánh trong kết quả.')
h2('Kiểm chứng bằng cùng thời điểm sinh gói')
table(['Điều kiện','Quan sát'],[
 ['Tf=1 ms, τ=5 µs; gói tại 1 ms và 2,002 ms; ALOHA','Cả hai hỏng vì tín hiệu cũ còn trên bus.'],
 ['Cùng thời điểm sinh nhưng τ=0','Cả hai thành công.'],
 ['Cùng τ=5 µs nhưng dùng CSMA/CD','Nút đến sau chờ kênh; cả hai thành công.'],
 ['Gói sau tại đúng 2,005 ms','Không va chạm tại biên nửa kín.'],
], [4,3],padding=5)
para('Bản cũ được giữ trong results/archive/before-common-phy.zip. Mọi kết quả chính trong tài liệu này thuộc bus phiên bản 2.', 'caption')

# 6
section('Bộ đếm gói và cửa sổ đo')
table(['Bộ đếm','Ý nghĩa'],[
 ['generated','Gói mới sinh; gồm cả gói bị chặn sau đó.'],['blocked','Gói bị chặn do FIFO đầy.'],
 ['success','Gói được ghi nhận hoàn thành thành công.'],['collisions','Lần thử thất bại do va chạm, không phải số đợt va chạm vật lý.'],
 ['dropped','Gói bị loại do hết số lần thử.'],['txAttempts','Lần bắt đầu thử truyền trong cửa sổ.'],
 ['retransmissions','Lần bắt đầu thử thứ hai trở đi.'],['resolvedAttempts','Lần thử đã được giải quyết thành công hoặc thất bại.'],
 ['initialPending','Gói còn tồn tại ở đầu cửa sổ đo.'],['finalPending','Gói chưa hoàn thành ở cuối cửa sổ đo.'],
 ['delaySum','Tổng độ trễ các gói hoàn thành.'],['carrierWaits','Số lần chờ vì cảm nhận kênh bận.'],
], [2.2,4.8],padding=5)
h2('Warmup và biên thời gian')
para('Run chuẩn 20 s bỏ 2 s đầu, đo trong 18 s; run dài 100 s bỏ 10 s đầu, đo trong 90 s. Bộ đếm dùng thời điểm sự kiện, không theo một cohort gói cố định.')
bullet('Gói sinh trước warmup nhưng kết thúc trong cửa sổ vẫn góp vào success và delay; delay tính từ lúc sinh thật.')
bullet('Khung phát xong nhưng đang chờ kết quả vẫn thuộc finalPending. Sự kiện đúng tại warmup được xử lý nhất quán.')
bullet('Kết thúc trước warmup tạo cửa sổ rỗng: dùng tồn cuối làm hai snapshot, các bộ đếm đo bằng 0; phân tích từ chối T=0.')
h2('Đối soát tồn kho từng nút')
para('initialPending + generated - blocked = success + dropped + finalPending')
para('Ví dụ seed 0, CSMA/CD, G=0,6: 3 + 10.708 = 10.709 + 2. Success lớn hơn generated một gói vì có gói tồn đầu kỳ, không phải tạo thêm gói.')
para('Thất bại CSMA/CD ghi tại phát hiện cục bộ; thành công và thất bại ALOHA ghi khi nhận kết quả bus. Lần thử cắt qua biên có thể được bắt đầu và giải quyết ở hai cửa sổ khác nhau.', 'small')

# 7
section('Công thức và cách tổng hợp kết quả')
para('Trong các công thức, bộ đếm được cộng toàn mạng; T là thời gian đo, B là frameBits và Tf là frameTime.')
table(['Chỉ tiêu','Công thức'],[
 ['Thông lượng chuẩn hóa S','success × Tf / T'],['Thông lượng bit/s','success × B / T'],
 ['Tải thử truyền quan sát','txAttempts × Tf / T'],['Tải gói mới quan sát','generated × Tf / T'],
 ['Tỷ lệ va chạm','collisions / resolvedAttempts'],['Độ trễ trung bình','delaySum / success'],
 ['Tỷ phần truyền lại','retransmissions / txAttempts'],['Tỷ số chặn/loại','(blocked + dropped) / generated'],
], [3,4],padding=6)
h2('Trung bình và độ lệch chuẩn')
para('Tính mỗi metric cho từng run trước. Với 5 seed: mean = (x1+...+x5)/5; SD mẫu = sqrt(Σ(xi-mean)^2/4). Thanh sai số là SD mẫu, không phải khoảng tin cậy. Delay được gộp theo số gói thành công trong từng run rồi mới lấy trung bình giữa run.')
para('Không có success thì delay không xác định, được giữ NaN. Các tỷ số mẫu số bằng 0 cũng là NaN. Cột *_valid_runs cho biết số seed có giá trị xác định; bộ dữ liệu chính hiện tại có đủ 5 seed hợp lệ cho mọi metric.')
h2('Ví dụ tính từ scalar của seed 0 tại G=0,6')
para('CSMA/CD: success=10.709; collisions=7.478; delaySum=23,6887626 s; T=18 s; Tf=0,001 s; B=10.000 bit.')
para('S = 10.709 × 0,001 / 18 = 0,594944\nThroughput = 10.709 × 10.000 / 18 = 5,949444 Mbps\nDelay = 23,6887626 / 10.709 = 2,212 ms\nCollision ratio = 7.478 / (7.478+10.709) = 41,117%')
para('Đây là một seed minh họa, khác số trung bình 5 seed ở trang kết quả. Tỷ số chặn/loại là tỷ số sự kiện trong cửa sổ, không phải xác suất mất của cùng một cohort. S không phải tỷ lệ gói sinh ra được giao thành công.', 'small')

# 8
section('Danh sách 32 kiểm thử tích hợp')
para('Các kiểm thử dưới đây đã đạt và được ghi trong results/tests/tests.json. Một điều kiện kiểm chứng có thể sử dụng nhiều cấu hình hoặc nhiều lượt chạy.', 'small')
integration_vn=[
 'Một nút truyền thành công, không va chạm.',
 'Hai nút cùng phát: va chạm, backoff và phục hồi.',
 'Giá trị BEB nằm trong cận cấu hình.',
 'Đạt giới hạn thử thì loại cả hai khung.',
 'Kênh bận làm nút đến sau chờ truyền.',
 'Hai khe Slotted kế tiếp không va chạm.',
 'Mọi lần phát Slotted đúng biên khe có guard.',
 'Tồn kho gói qua warmup được đối soát đúng.',
 'Từ chối Tf quá ngắn và trường hợp Tf=2τ.',
 'Từ chối thời lượng không hợp lệ và mạng không có nút.',
 'Pure ALOHA: khoảng phát chồng lấn làm hỏng cả hai.',
 'Pure ALOHA: hai khoảng kề nhau tại trễ 0 không va chạm.',
 'Phần đuôi tín hiệu làm hỏng cả hai sau END của nguồn đầu.',
 'Cùng thời điểm phát thành công khi trễ bằng 0.',
 'Đúng biên hết phần đuôi không bị va chạm.',
 'Dùng trễ theo cặp nút, không áp cận mạng cho mọi cặp.',
 'Trễ lớn gây va chạm dù nguồn không phát chồng thời gian.',
 'Guard bảo vệ hai khe kế tiếp khi trễ lớn.',
 'CSMA chờ đúng phần đuôi làm hỏng ALOHA.',
 'Khung còn pending đến khi có kết quả bus chung.',
 'Dừng khi jam còn phản hồi đang bay vẫn bảo toàn gói.',
 'Cùng khe ALOHA va chạm rồi phục hồi ở khe hợp lệ.',
 'BEB cap 0: mỗi K đúng giai đoạn và cận.',
 'BEB cap 0: hết đúng 4 lần thử cho mỗi khung.',
 'BEB cap 2: mỗi K đúng giai đoạn và thật sự chạm cap.',
 'Gói sinh đúng warmup được tính trong cửa sổ.',
 'Hoàn thành đúng warmup giải quyết gói tồn đầu kỳ.',
 'Kết thúc trước warmup ghi cửa sổ đo bằng 0.',
 'Cùng seed tái lập toàn bộ scalar của các nút.',
 'Pure ALOHA nhận cùng lưu lượng gói mới với CSMA/CD.',
 'Slotted ALOHA nhận cùng lưu lượng gói mới với CSMA/CD.',
 'Tràn FIFO được ghi nhận và giữ đúng đối soát gói.',
]
assert len(integration_vn)==len(tests['passed'])
table(['STT','Điều kiện đã kiểm tra'],list(enumerate(integration_vn,1)),[.55,6.45],size=9.1,padding=2.5)

# 9
section('14 kiểm thử workflow và tái lập dữ liệu')
workflow_vn=[
 'Không đưa scalar cũ ngoài manifest vào phân tích.',
 'Nguồn C++ thay đổi thì yêu cầu build lại.',
 'Script phân tích thay đổi thì từ chối batch trước đó.',
 'Executable thay đổi thì yêu cầu bản build tương ứng.',
 'Scalar bị sửa thì từ chối.',
 'Thiếu log thì từ chối.',
 'Run thiếu hoặc trùng thì từ chối.',
 'Batch thất bại/chưa hoàn tất thì từ chối.',
 'Metadata trong manifest phải khớp scalar.',
 'Seed không có gói hoàn thành có số run hợp lệ rõ ràng.',
 'Mẫu số bằng 0 được giữ là không xác định.',
 'Seed trùng trong bộ tham số bị từ chối.',
 'So sánh khác điều kiện vật lý/lưu lượng bị từ chối.',
 'Scalar mô hình vật lý cũ hoặc không nhất quán bị từ chối.',
]
table(['STT','Kiểm thử đã đạt'],list(enumerate(workflow_vn,1)),[.55,6.45],padding=4)
h2('Chuỗi kiểm chứng dữ liệu')
para('Build thành công → build-info.json → runner kiểm tra fingerprint → truy vấn số run từ OMNeT++ → ghi từng kết quả và manifest → chỉ phân tích batch complete → kiểm tra nguồn, executable, hash file, metadata, tồn kho, seed và điều kiện so sánh → CSV và biểu đồ.')
para('Manifest ghi cấu hình, run, seed, tham số NED thực tế, thời gian đo, thời gian chạy, phiên bản công cụ và mã băm. Nguồn/executable thay đổi trong batch bị phát hiện. Kiểm thử được lưu riêng, tránh ghi đè dữ liệu nghiên cứu.')
para('Không dùng ketqua.csv cũ. File tồn tại nhưng không thuộc manifest không tự trở thành dữ liệu đã xác minh. Khi chạy lại tập cấu hình con, manifest thể hiện đúng tập con đó; muốn bộ đầy đủ phải dùng lệnh thí nghiệm mặc định.', 'small')

# 10
section('Ma trận thí nghiệm đã hoàn thành')
para('Ba mức tải chính là nhẹ G=0,1; trung bình G=0,6; cao G=1,5. Các con số 3 kịch bản, 7 nhóm, 69 bộ tham số và 345 lượt là các cách đếm khác nhau.')
table(['Nhóm','Thiết kế','Bộ','Lượt'],[
 ['CsmaCd','9 mức G','9','45'],['Aloha','Cùng 9 mức G','9','45'],['Slotted','Cùng 9 mức G','9','45'],
 ['StudyN','4 giá trị N × 3 mức G','12','60'],['StudyA','5 giá trị a × 3 mức G','15','75'],
 ['StudyBEB','4 cap BEB × 3 mức G','12','60'],['Stability','3 mức G, chạy dài','3','15'],
 ['Tổng','Mỗi bộ 5 seed 0-4','69','345'],
], [1.4,3.8,.8,1],padding=6)
h2('Dải giá trị đã chạy')
table(['Khảo sát','Giá trị'],[
 ['So sánh 3 MAC','G = 0,05; 0,1; 0,2; 0,4; 0,6; 0,8; 1; 1,5; 2.'],
 ['Số nút','N = 5; 10; 20; 50. G = 0,3; 0,6; 1.'],
 ['Tỷ lệ trễ','a = τ/Tf = 0,01; 0,05; 0,1; 0,25; 0,4. G = 0,3; 0,6; 1.'],
 ['BEB','Cap = 2; 4; 6; 10. N=20, G = 0,3; 0,6; 1.'],
 ['Stability','CSMA/CD tại G = 0,1; 0,6; 1,5.'],
], [1.5,5.5],padding=6)
para('Run chuẩn: 20 s, warmup 2 s, Tđo=18 s. Run dài: 100 s, warmup 10 s, Tđo=90 s. Tổng hợp dùng trung bình và SD mẫu giữa 5 seed; mọi metric của 69 nhóm hiện có đủ 5 seed hợp lệ.')
para('Sau khi đổi sang bus chung đã chạy lại toàn bộ 345 lượt. Tổng thời gian tiến trình mô phỏng ghi trong manifest khoảng 220 giây, không phải thời gian mô phỏng và không dùng làm chỉ số hiệu năng mạng.', 'small')

# 11
section('Kết quả so sánh ba giao thức')
para('Bảng và biểu đồ dùng trung bình 5 seed của bus phiên bản 2. Thông lượng tính theo bit khung mô hình, không phải goodput payload ứng dụng.', 'small')
result_rows=[]
labels={'CsmaCd':'CSMA/CD','Aloha':'Pure ALOHA','Slotted':'Slotted ALOHA'}
for g in [.1,.6,1.5]:
    for config in ['CsmaCd','Aloha','Slotted']:
        r=find(config,g)
        result_rows.append([fmt(g,1),labels[config],fmt(r['S_mean']),fmt(float(r['throughput_bps_mean'])/1e6),fmt(float(r['delay_s_mean'])*1000,3)])
table(['G','MAC','S','Mbps','Delay ms'],result_rows,[.55,1.8,1.4,1.5,1.3],padding=4)
plot('comparison_S.png','Hình 1. Thông lượng chuẩn hóa theo tải gói mới G; thanh sai số là SD mẫu giữa 5 seed.')
para('Tải nhẹ: S gần bằng nhu cầu ở cả ba, nhưng delay CSMA/CD thấp hơn. Tải lớn: CSMA/CD đạt S cao hơn trong mô hình này; Slotted cao hơn Pure ALOHA. Khi G=1,5, nguồn yêu cầu khoảng 1.500 gói/s, vượt trần lý tưởng 1.000 khung/s của khung 1 ms; hàng đợi hữu hạn dẫn đến chặn/loại.')
para('Không áp trực tiếp đường lý thuyết ALOHA theo G gói mới: truyền lại tạo tải thử thêm, nguồn thử không thỏa giả định Poisson độc lập lý tưởng. Kết luận chỉ áp dụng cho mô hình và backoff đã nêu.', 'small')

# 12
section('Khảo sát số nút và giới hạn BEB')
h2('Số nút tại G=1')
nrows=sorted((r for r in summary if r['config']=='StudyN' and float(r['G'])==1),key=lambda r:float(r['N']))
table(['N','S trung bình','Delay trung bình ms'],[[r['N'],fmt(r['S_mean']),fmt(float(r['delay_s_mean'])*1000,3)] for r in nrows],[1,2,3],padding=4)
plot('StudyN.png','Hình 2. Khảo sát N ở ba mức tải; mỗi điểm có 5 seed.',width=WIDTH*.88)
para('Trong lát cắt G=1, S tăng cùng N nhưng delay cũng tăng. QueueLimit cố định 10 gói/nút làm tổng dung lượng hàng đợi tăng theo N. Không suy ra quy luật chung rằng càng nhiều nút thì mạng càng tốt.', 'small')
h2('BEB tại G=1 và N=20')
brows=sorted((r for r in summary if r['config']=='StudyBEB' and float(r['G'])==1),key=lambda r:float(r['beb']))
table(['Cap số mũ','S trung bình','Delay trung bình ms'],[[r['beb'],fmt(r['S_mean']),fmt(float(r['delay_s_mean'])*1000,3)] for r in brows],[1.5,2,3],padding=4)
para('S không tăng đơn điệu theo cap. Cửa sổ lớn có thể giảm tranh chấp nhưng tăng thời gian chờ; cap 6 có S cao nhất trong lát cắt này, không phải kết luận tối ưu cho mọi cấu hình. Biểu đồ BEB đầy đủ ở phụ lục.', 'small')

# 13
section('Khảo sát tỷ lệ trễ lan truyền')
para('Tham số a = τ/Tf được thay đổi trong khi Tf=1 ms. Bảng là lát cắt G=1; biểu đồ thể hiện đủ ba mức tải được khảo sát.')
arows=sorted((r for r in summary if r['config']=='StudyA' and float(r['G'])==1),key=lambda r:float(r['a']))
table(['a','S trung bình','Delay trung bình ms'],[[fmt(r['a'],2),fmt(r['S_mean']),fmt(float(r['delay_s_mean'])*1000,3)] for r in arows],[1,2,3],padding=5)
plot('StudyA.png','Hình 3. Khi tăng a, slot BEB và thời gian chờ kết quả cũng thay đổi theo cấu hình.')
para('Trong khảo sát này, tăng a đi cùng giảm S và tăng delay. Tại G=1, S giảm từ 0,888211 xuống 0,585978; delay tăng từ 28,539 ms lên 86,739 ms.')
para('Không quy riêng toàn bộ thay đổi cho thời gian phát hiện va chạm: code dùng slot=max(512/R,2τ) và thời gian chờ cuối khung τ. Các chi phí này cùng thay đổi. Tỷ lệ va chạm giảm cũng không tự động đồng nghĩa thông lượng tăng.', 'small')

# 14
section('Kiểm tra độ ổn định theo thời lượng')
para('So sánh hai thiết lập CSMA/CD: run 20 s/warmup 2 s và run 100 s/warmup 10 s. Mỗi thiết lập có 5 seed tại ba mức tải chính.')
srows=[r for r in stability if r['metric']=='S']
table(['G','S run 20s','S run 100s','Thay đổi'],[
 [fmt(r['G'],1),fmt(r['short_mean']),fmt(r['long_mean']),f"{float(r['relative_change'])*100:+.4f}%".replace('.',',')]
 for r in srows],[.7,2,2,1.6],padding=6)
plot('Stability.png','Hình 4. Đối chiếu S; thanh sai số là SD mẫu của từng nhóm 5 seed.')
para('Thông lượng trung bình tại ba mức tải thay đổi dưới khoảng 0,7%. Đây là kiểm tra độ nhạy theo thời lượng cho S ở các cấu hình đã chạy, không chứng minh mọi metric đều ổn định như nhau.')
para('File results/summary/stability.csv có 12 hàng: 3 mức G × 4 metric gồm S, collision_ratio, delay_s và loss_ratio. Mỗi hàng ghi mean/SD của hai thời lượng cùng thay đổi tương đối.', 'small')

# 15
section('Demo thực tế và diễn biến một lần chạy')
para('Đã chạy Qtenv, kiểm tra scalar khớp với Cmdenv và chạy thêm 16 lượt minh họa: 7 cấu hình nhỏ, cộng 3 MAC × 3 mức tải với seed 0. Dữ liệu được lưu riêng ở results/explanation; không thay thế bộ 345 lượt chính.', 'small')
demo_configs=[('TestSingle','Một nút'),('TestCollision','Cùng phát'),('TestDrop','Giới hạn 1 lần thử'),('TestWait','Chờ kênh bận'),('TestPropagationTail','ALOHA gặp phần đuôi'),('TestCsmaPropagationTail','CSMA gặp cùng phần đuôi'),('TestSlotted','Hai khe có guard')]
drows=[]
for config,label in demo_configs:
    _,nodes=read_sca(ROOT/f'results/explanation/{config}-0.sca')
    t=totals(nodes)
    drows.append([label,str(int(t['success'])),str(int(t['collisions'])),str(int(t['retransmissions'])),str(int(t['dropped']))])
table(['Kịch bản','Thành công','Thử va chạm','Truyền lại','Loại'],drows,[2.6,1.15,1.15,1,1],size=8.8,padding=4)
h2('Timeline TestCollision seed 0')
table(['Thời điểm ms','Diễn biến'],[
 ['1,000','Hai nút cùng phát.'],['1,005','Phát hiện va chạm sau 5 µs; bắt đầu jam.'],
 ['1,0082','Hết jam; cả hai chọn K=1.'],['1,0594','Cùng thử lại, lại va chạm.'],
 ['1,0676','Hết jam lần hai; cả hai chọn K=0.'],['1,0726','Kênh hết tín hiệu cũ; cùng phát lần ba và va chạm.'],
 ['1,0808','Nút 0 chọn K=7, nút 1 chọn K=1.'],['1,132','Nút 1 phát; nút 0 sau đó chờ vì kênh bận.'],
 ['2,137 / 3,142','Nút 1 thành công và nút 0 bắt đầu; sau đó nút 0 thành công.'],
], [1.4,5.6],size=9,padding=3)
para('Ba đợt va chạm × hai lần thử = 6 lần thử thất bại. Hai gói có tổng 8 lần thử, 6 truyền lại. Trong T=10 ms: S=2×1/10=0,2; throughput=2 Mbps; collision ratio=6/8=75%; delay trung bình=(1,137+2,142)/2=1,6395 ms.', 'small')
para('S=0,2 trong test này do chỉ sinh hai gói rồi để rỗi tới 10 ms, không phải giới hạn hiệu năng của CSMA/CD. Thời gian hoạt ảnh Qtenv trên máy khác thời gian mô phỏng.', 'small')

# 16
section('Các file đã chỉnh sửa hoặc bổ sung')
table(['File trong BTL_MMT','Vai trò và phần việc'],[
 ['Node.cc','MAC, FIFO, backoff, xử lý kết quả, biên warmup, kiểm tra tham số và thống kê.'],
 ['Node.h','Trạng thái, timer, bộ đếm và mã lần thử.'],
 ['Bus.cc','Bus chung, trễ theo vị trí, lịch sử phần đuôi và kết quả truyền.'],
 ['CsmaCd.ned','Topology, tham số, signal/statistic và quan sát số mũ BEB.'],
 ['omnetpp.ini','7 nhóm thí nghiệm và các cấu hình kiểm thử.'],
 ['scripts/build.ps1','Môi trường build, make release và build-info.json.'],
 ['scripts/run.py','Runner, integration checks, manifest và xác minh kết quả.'],
 ['scripts/analyze.py','Tính metric, kiểm tra phép so sánh, CSV, biểu đồ và stability.'],
 ['scripts/test_workflow.py','14 kiểm thử workflow và tính đúng của tổng hợp.'],
 ['CsmaCd.anf','Sửa đường dẫn đọc kết quả trong IDE.'],
 ['README.md','Môi trường, lệnh chạy, công thức, quy ước và giới hạn.'],
 ['REVIEW.md','Các lỗi đã xử lý, kiểm chứng và đối chiếu trước-sau.'],
 ['demo/DEMO.md','Kịch bản trình diễn 3-5 phút, gồm kiểm thử bus chung.'],
 ['report/CONTRIBUTIONS.md','Mẫu phân công và nhật ký; chưa điền dữ liệu thực tế.'],
 ['F:/BTL_MMT_detai/PLAN.md','Kế hoạch và hợp đồng mô hình chung được cập nhật.'],
], [2.7,4.3],padding=4)
h2('Các lệnh chạy lại')
for command in ['./scripts/build.ps1','python scripts/run.py test','python -m unittest discover -s scripts -p test_workflow.py -v','python scripts/run.py experiments','python scripts/analyze.py']:
    para(command, 'code')
para('Cần Python phù hợp, OMNeT++ 6.4.0 và matplotlib cho biểu đồ. Đường dẫn công cụ được suy ra từ vị trí dự án samples/BTL_MMT; đặt dự án ở nơi khác cần kiểm tra lại theo README.', 'small')

# 17
section('Bộ dữ liệu và sản phẩm đang có')
table(['Vị trí','Nội dung'],[
 ['results/verified/','Scalar/log của 345 lượt và manifest complete; chỉ các run trong manifest là bộ chính.'],
 ['results/tests/','Scalar/vector/log của kiểm thử cơ chế và tests.json có 32 điều kiện đạt.'],
 ['results/summary/runs.csv','Metric toàn mạng từng lượt; 345 hàng dữ liệu.'],
 ['results/summary/summary.csv','69 nhóm; mean, SD và số seed hợp lệ.'],
 ['results/summary/stability.csv','12 đối chiếu metric giữa hai thời lượng.'],
 ['results/explanation/','16 lượt CLI minh họa và một lượt GUI đối chiếu; walkthrough.json.'],
 ['results/archive/before-common-phy.zip','Bản lưu trước bus chung; không phải ZIP nộp bài.'],
 ['plots/','10 biểu đồ PNG được dựng từ scalar đã xác minh.'],
 ['build-info.json','Fingerprint nguồn biên dịch và executable sau build thành công.'],
], [3.1,3.9],padding=5)
h2('Danh mục 10 biểu đồ')
table(['Tên file','Nội dung'],[
 ['comparison_S.png','Thông lượng chuẩn hóa S'],['comparison_collision_ratio.png','Tỷ lệ lần thử va chạm'],
 ['comparison_delay_s.png','Delay gói thành công'],['comparison_loss_ratio.png','Tỷ số chặn/loại'],
 ['comparison_success.png','Số gói thành công'],['comparison_retransmissions.png','Số lần truyền lại'],
 ['StudyN.png / StudyA.png','Khảo sát số nút / tỷ lệ trễ'],['StudyBEB.png / Stability.png','Khảo sát BEB / đối chiếu thời lượng'],
], [3.7,3.3],padding=3)
para('Bộ cũ được lưu để so sánh lịch sử. Thay đổi kết quả trước-sau là tác động tổng hợp của quy tắc phần đuôi, thời gian chờ kết quả chung và guard Slotted; không quy toàn bộ thay đổi cho một yếu tố riêng.', 'small')

# 18
section('Giới hạn và công việc còn lại')
table(['Hạng mục','Trạng thái cần hoàn thiện'],[
 ['Báo cáo nộp chính thức','Chưa có bản đầy đủ theo cấu trúc của đề; PDF hiện tại là tổng hợp công việc.'],
 ['Slide bảo vệ','Chưa có.'],['Video/bộ minh chứng','Có kịch bản và log; chưa biên tập thành bộ nộp cuối.'],
 ['Thông tin nhóm','Chưa điền đủ 5 tên/MSSV, học kỳ và số nhóm.'],
 ['Nhật ký đóng góp','Mẫu còn trống; phải điền từ công việc có thật.'],
 ['Phê duyệt phạm vi','Chưa có thông tin xác nhận của giảng viên.'],
 ['ZIP nộp bài','Chưa đóng gói và nghiệm thu theo quy ước ET4230_HK[ky]_N[so-nhom]_D03.zip.'],
 ['Chạy từ bản giải nén','Chưa kiểm tra ở thư mục hoặc máy khác.'],
 ['Bảo vệ cá nhân','Mỗi thành viên cần tự thao tác, đọc mã/dữ liệu và giải thích phần phụ trách.'],
], [2.1,4.9],padding=5)
h2('Giới hạn kỹ thuật phải nêu khi bảo vệ')
para('Dùng phản hồi oracle chung, chưa hiện thực ACK. Mô hình broadcast bảo thủ không có đầu thu đích/capture effect, IFG, preamble, địa chỉ MAC, CRC, lỗi bit và tầng trên. FrameBits là bit khung mô hình. Không suy rộng thành switched Ethernet full-duplex hay hiện thực đầy đủ IEEE 802.3.')
para('Các quan sát về N, a và BEB gắn với FIFO hữu hạn, backoff, thông số và thời lượng đã chạy. Tỷ số chặn/loại theo sự kiện không phải xác suất mất cohort; thanh sai số là SD mẫu, không phải khoảng tin cậy.', 'small')
h2('Nguồn nội bộ để đối chiếu')
para('Thư mục dự án: F:/omnet++/omnetpp-6.4.0/samples/BTL_MMT\nĐề gốc: F:/BTL_MMT_detai/ET4230_Bai_tap_lon_Mo_phong_CAP_NHAT_2026.docx\nKế hoạch: F:/BTL_MMT_detai/PLAN.md\nREADME.md, REVIEW.md, omnetpp.ini\nresults/tests/tests.json; results/verified/manifest.json\nresults/summary/runs.csv; summary.csv; stability.csv\nresults/explanation/walkthrough.json', 'small')
para('AI hỗ trợ rà soát/sửa mã, viết script, chạy kiểm chứng và soạn tài liệu. Nhóm chịu trách nhiệm đọc, kiểm thử, trích dẫn nguồn kế thừa và bảo vệ nội dung; không có đóng góp hay phê duyệt nào được tự gán.', 'small')

# 19-21: all remaining plots are included once.
appendices=[
 ('Phụ lục biểu đồ va chạm và độ trễ',[
    ('comparison_collision_ratio.png','Hình 5. Lần thử va chạm / lần thử đã giải quyết.'),
    ('comparison_delay_s.png','Hình 6. Delay trung bình các gói hoàn thành trong từng run, rồi trung bình giữa seed.')]),
 ('Phụ lục biểu đồ chặn loại và thành công',[
    ('comparison_loss_ratio.png','Hình 7. (Blocked+dropped)/generated theo sự kiện trong cửa sổ đo.'),
    ('comparison_success.png','Hình 8. Số gói thành công trong cửa sổ đo 18 s.')]),
 ('Phụ lục biểu đồ truyền lại và BEB',[
    ('comparison_retransmissions.png','Hình 9. Lần bắt đầu thử thứ hai trở đi trong cửa sổ đo.'),
    ('StudyBEB.png','Hình 10. Ảnh hưởng cap số mũ BEB; N=20, ba mức tải.')]),
]
for title,images in appendices:
    section(title)
    para('Mô hình bus chung phiên bản 2. Giá trị là mean và SD mẫu giữa 5 seed.', 'small')
    for filename,caption in images:
        plot(filename,caption)

doc = SummaryDoc(str(OUT), pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                 topMargin=MARGIN, bottomMargin=MARGIN,
                 title='Tổng hợp công việc và kết quả mô phỏng CSMA/CD',
                 author='Tổng hợp kỹ thuật dự án BTL_MMT',
                 subject='ET4230 Đề 03 - mô hình, kiểm thử, thí nghiệm và phần còn lại')
doc.build(STORY,onFirstPage=footer,onLaterPages=footer)
reader=PdfReader(OUT)
sections=doc.sections
print(json.dumps({'output':str(OUT),'pages':len(reader.pages),'bytes':OUT.stat().st_size,
                  'sections':sections},ensure_ascii=False,indent=2))
(ROOT/'tmp/pdfs/page_map.json').write_text(json.dumps(sections,ensure_ascii=False,indent=2),encoding='utf-8')
# Explicit page ownership catches accidental overflow and stale contents locators.
assert len(reader.pages)==21, f'Expected 21 pages, got {len(reader.pages)}'
assert [s['page'] for s in sections]==list(range(1,22)), 'A section overflowed its planned page'
text='\n'.join(page.extract_text() or '' for page in reader.pages)
for required in ['345','69','32','14','1,005','0,925433','Chưa kiểm tra','Slotted ALOHA']:
    assert required in text,required
assert '\ufffd' not in text
assert all('/FontFile2' in str(font.get_object().get('/FontDescriptor',{}).get_object())
           for page in reader.pages for font in page['/Resources']['/Font'].values()
           if font.get_object().get('/Subtype')=='/TrueType')
