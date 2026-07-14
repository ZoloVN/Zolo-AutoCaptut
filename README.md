# ZOLO Auto CapCut v2.0
<img style="display: block;-webkit-user-select: none;margin: auto;cursor: zoom-in;background-color: hsl(0, 0%, 90%);transition: background-color 300ms;" src="https://raw.githubusercontent.com/ZoloVN/Zolo-AutoCaptut/refs/heads/main/screenshot_1783997876.png" width="595" height="544">

<img style="display: block;-webkit-user-select: none;margin: auto;cursor: zoom-in;background-color: hsl(0, 0%, 90%);transition: background-color 300ms;" src="https://raw.githubusercontent.com/ZoloVN/Zolo-AutoCaptut/refs/heads/main/screenshot_1783997771.png" width="682" height="544">

Tool tự động hoá cho CapCut PC, thao tác trực tiếp vào `draft_content.json` thay vì
giả lập chuột/phím (khác với các tool "Auto CapCut" bán trên thị trường).

## Mask + Chuyển động đa dạng + Text Animation (mới - từ phân tích file app-64.7z)

Bạn gửi file `app-64.7z` (bản đóng gói đầy đủ của VibeCut) và yêu cầu "bê hết qua".
Thử decompile phần lõi Python (`resources/server/app/src/service/*.pyc`) nhưng
**không giải mã được** - các file này biên dịch cho Python 3.12, các công cụ decompile
hiện có (`decompyle3`, `uncompyle6`) chưa hỗ trợ version này (test trực tiếp, báo lỗi
"Unsupported Python version, 3.12.0").

Tuy không lấy được mã nguồn, phần docstring/comment còn sót lại trong bytecode
(không bị xoá khi biên dịch) tiết lộ đủ thông tin để tự làm lại bằng chính thư viện
`pyJianYingDraft` công khai:
- `add_masks.pyc`: dùng `MaskType`, tham số `width/height/feather/rotation/invert/roundCorner`
- `add_sticker.pyc`: dùng `StickerSegment`
- `add_keyframes_auto.pyc`: **có comment tiếng Việt của dev gốc** - "Ken Burns effect...
  thêm keyframe zoom/pan/rotate ngẫu nhiên", các preset đặt tên "Zoom In/Zoom Out/Pan Right"
- `add_captions.pyc`: dùng `TextIntro/TextOutro/TextLoopAnim` - xác nhận sub có animation
  riêng, không chỉ animation cho ảnh/video

Đã tự build lại cả 3 bằng `pyJianYingDraft` (đã test resource_id thật, không phải đoán):

- **Mask**: `effects_module.decorate_mask()` - tròn/chữ nhật/tuyến tính, gắn lúc dựng segment.
- **Chuyển động đa dạng**: `effects_module.decorate_motion()` - 7 preset (zoom in/out,
  pan trái/phải/lên/xuống, xoay nhẹ) thay cho Ken Burns cơ bản trước đây (vẫn giữ Ken Burns
  làm lựa chọn đơn giản, KHÔNG bật cùng lúc với Motion để tránh xung đột keyframe).
- **Text animation cho sub**: `captions_module.import_srt_with_animation()` - tự parse SRT
  (tái dùng `srt_tstamp()` gốc của thư viện để không lệch định dạng thời gian), gắn
  `TextIntro` riêng cho từng dòng, lặp vòng qua pool (mặc định:渐显/打字机_I/波浪弹入).
  Trong giao diện Web, tick "Gắn animation cho từng dòng sub" trong tab Sub/Caption.

**Sticker: đã làm được, giờ chạy 100% cục bộ** (chi tiết ở mục "Kiến trúc mới" ngay
dưới đây - ban đầu định gọi cloud công khai `capcut-mate.jcaigc.cn`, sau khi bạn hỏi
về Docker đã chuyển hẳn sang vendor server chạy local, không phụ thuộc mạng ngoài nữa).
Test thật: tìm "爱心" (trái tim) và "星" (sao) đều ra 50 kết quả có ảnh preview, chèn
vào draft thành công qua UI.

## Kiến trúc mới: chạy kèm capcut_mate_engine (giống VibeCut)

Bạn hỏi tool tham khảo (VibeCut) có dùng Docker không - **không**, họ đóng gói sẵn 1
server Python (PyInstaller) chạy như tiến trình con cục bộ. ZOLO giờ làm y hệt vậy,
nhưng dùng Python thuần (venv) thay vì đóng gói .exe, khớp quy ước ZOLO có sẵn.

**`capcut_mate_engine/`** là bản vendor rút gọn của dự án mã nguồn mở
[capcut-mate](https://github.com/Hommy-master/capcut-mate) (Apache 2.0, giữ nguyên
LICENSE/NOTICE) - chính là nền tảng VibeCut xây dựa trên. Đã bỏ bớt phần không cần:
`tools/ffprobe` (75MB, dùng ffmpeg hệ thống thay), `desktop-client` (Electron, ZOLO có
UI riêng), `tests/`. Giữ lại `config/sticker.json` (59MB - catalog sticker đầy đủ, xem
bên dưới).

**Dùng để làm gì:** chỉ dùng làm dịch vụ TRA CỨU cục bộ (sticker search, có thể mở
rộng effect/filter catalog sau) - **không** dùng cơ chế dựng draft của họ (kiến trúc
"tải draft qua URL" của họ hợp với multi-user/cloud hơn, trong khi `draft_builder.py`
của ZOLO ghi thẳng vào thư mục CapCut - tiện hơn cho máy đơn).

- Chạy `run_web.bat` sẽ tự khởi động CẢ 2: `capcut_mate_engine` (cổng 30000, chạy nền)
  + ZOLO server (cổng 5757, giao diện chính).
- **Sticker giờ tìm 100% cục bộ** - test thật: tìm "爱心" (trái tim) ra 50 kết quả có
  ảnh preview thật, tìm "星" (sao) cũng ra 50 kết quả - không cần internet, không phụ
  thuộc `capcut-mate.jcaigc.cn` (cloud công khai) nữa.
- Nếu quên chạy `capcut_mate_engine`, tab Sticker báo lỗi rõ ràng (không tự động thử
  gọi cloud, tránh phụ thuộc ngầm ngoài ý muốn).

**Tiềm năng chưa khai thác hết:** `capcut_mate_engine/src/pyJianYingDraft/jianying_controller.py`
là bộ điều khiển UI automation cục bộ RẤT chỉn chu (state machine, retry COM error, xử
lý đúng luồng export) - tốt hơn nhiều so với `auto_render.py` sơ khai của ZOLO. Nhưng
đang hard-code nhận diện cửa sổ **"剪映专业版"** (JianYing nội địa Trung Quốc), CHƯA
có tên cửa sổ CapCut quốc tế - cần chỉnh + test trên CapCut thật mới dùng được. Nếu
muốn làm Auto Render thật sự đáng tin cậy, đây là điểm khởi đầu tốt hơn nhiều so với
viết lại từ đầu bằng pywinauto.

## 2 giao diện, cùng 1 lõi xử lý

- **Giao diện Web (mới, khuyến nghị)**: chạy `run_web.bat`, mở tại `http://127.0.0.1:5757`.
  Đẹp hơn, waveform mượt hơn (Canvas thật của trình duyệt), nghe thử bằng thẻ `<audio>`
  chuẩn thay vì pygame. Thiết kế theo ngôn ngữ màu "orange & teal" quen thuộc với dân
  dựng phim (color grading), font monospace cho timecode/nhãn kỹ thuật.
- **Giao diện tkinter (bản cũ)**: chạy `run.bat`. Vẫn giữ nguyên, dùng khi không muốn
  mở trình duyệt hoặc máy yếu.

Cả 2 giao diện dùng chung `draft_utils.py`, `audio_splitter.py`, `draft_builder.py`,
`effects_module.py`, `captions_module.py`, `audio_sync.py` - sửa logic ở 1 chỗ, cả 2
giao diện đều được cập nhật.

## Trạng thái các module

| Module | Trạng thái | Ghi chú |
|---|---|---|
| Đồng bộ âm thanh | ✅ Đã test, chạy được ngay | Thuần JSON, có backup tự động, có ripple-shift tránh khoảng trống |
| Audio Splitter | ✅ Đã test, chạy được ngay | Tách audio dài theo khoảng lặng (giống VibeCut), dùng ffmpeg silencedetect |
| Draft Builder | ✅ Đã test, chạy được ngay | Ghép ảnh/video + audio thành draft CapCut hoàn chỉnh, dùng pyJianYingDraft + create_draft |
| Effects/Filters/Keyframes | ✅ Đã test, chạy được ngay | Gắn NGAY lúc dựng draft (xem lý do kỹ thuật bên dưới) - intro animation, transition, filter, Ken Burns zoom |
| Captions/Sub (Import/Export SRT) | ✅ Đã test, chạy được ngay | Import SRT đã dịch vào draft hàng loạt, export ngược lại để review |
| Auto Render | ⚠️ Cần calibrate trên máy Windows thật | Xem mục "Calibrate Auto Render" bên dưới - KHÔNG bắt buộc, bạn có thể Export tay |

## Cài đặt

1. Copy cả thư mục này vào `C:\TOOLS\ZOLO_AutoCapCut\`
2. Chạy `setup.bat` (tạo venv, cài dependencies cho cả ZOLO lẫn `capcut_mate_engine`)
3. Chạy `run_web.bat` (giao diện Web - khuyến nghị, tự khởi động cả `capcut_mate_engine`)
   hoặc `run.bat` (giao diện tkinter cũ - KHÔNG có tab Sticker, vì module đó cần
   `capcut_mate_engine` đang chạy)

**⚠️ Chạy bằng double-click bình thường, KHÔNG "Run as Administrator".** Nếu chạy
bằng quyền Admin (hoặc qua 1 số shortcut), Windows đặt thư mục làm việc thành
`C:\Windows\System32` thay vì thư mục chứa file `.bat`, khiến `venv` bị tạo nhầm chỗ
và báo lỗi `Could not open requirements file`. Đã sửa cả 3 file `.bat` tự `cd` về đúng
thư mục của chính nó trước khi chạy (bù trường hợp này), nhưng nếu đã lỡ chạy Admin 1
lần trước đó, xoá tay thư mục rác `C:\Windows\System32\venv` (cần quyền Admin để xoá,
không ảnh hưởng gì tới Windows) rồi chạy lại `setup.bat` bình thường.

## Video Splitter - dùng ngay được (tính năng mới)

Tách video dài theo khoảng lặng lời nói - giống "Video Splitter (Tách nhịp)" của
VibeCut. Tái dùng TOÀN BỘ logic phân tích + waveform của Audio Splitter (đã verify:
ffmpeg tự tách audio từ file video để phân tích, không cần viết lại code).

- Chọn file video, xem waveform (giống Audio Splitter), kéo chỉnh điểm cắt/nghe thử
  từng đoạn như bình thường.
- **Mỗi đoạn có 2 nút chuyển trạng thái:**
  - **🔇 Chỉ giữ tiếng**: xuất file `.mp3` (bỏ hình) thay vì `.mp4` - dùng khi hình
    gốc đoạn đó bị lỗi/rung nhưng tiếng vẫn ổn, tự chèn B-roll thay vào sau.
  - **🗑 Xoá đoạn**: bỏ qua hoàn toàn, không xuất file - dùng cho đoạn nói vấp/lỗi.
- Test thật: đoạn đánh dấu audio-only xuất đúng file `.mp3` thật (xác nhận bằng
  `file` command: MPEG audio layer III), đoạn đánh dấu xoá không xuất gì cả.

## Draft Picker - dropdown gọn nhúng trong panel (theo phản hồi mới nhất)

Bạn góp ý đúng: sidebar Draft List (dù đã ẩn/hiện theo tab) vẫn là 1 danh sách dài
chiếm chỗ, trong khi thực tế **thường chỉ chọn 1 draft mới nhất**, lâu lâu mới chọn
draft cũ hoặc vài cái cùng lúc. Đã bỏ hẳn sidebar, thay bằng **dropdown gọn nhúng
ngay trong từng panel cần dùng** (Sync, Sub/Caption, Sticker, Voice Align khi chọn
"Dùng draft đã chọn"):

- Nút gọn hiển thị tên draft đang chọn (hoặc "Chưa chọn draft ▾") - bấm để mở dropdown
  tìm kiếm, không chiếm chỗ khi đóng.
- **Sticker & Voice Align (existing draft)**: single-select - chọn 1 cái là tự đóng
  dropdown luôn, đúng nhịp "chọn 1 cái chính" thường gặp.
- **Sync & Sub/Caption**: multi-select - chọn nhiều cái, dropdown ở lại mở, có nút
  "Chọn tất cả"/"Bỏ chọn" cho trường hợp cần xử lý hàng loạt.
- Tất cả instance dùng chung 1 trạng thái lựa chọn - tick ở panel này, panel khác
  cũng thấy đồng bộ. **Lưu ý:** vì dùng chung 1 khái niệm "đang chọn draft nào", chọn
  single ở 1 panel (vd Sticker) sẽ THAY THẾ lựa chọn multi đã chọn ở panel khác (vd
  Sync) - đã test xác nhận đúng hành vi này, phù hợp với cách dùng thực tế (chọn 1
  cái chính là chủ yếu).

## Draft List - giờ tự ẩn/hiện theo tab (theo phản hồi)

*(Đã thay bằng Draft Picker gọn ở trên - giữ đoạn này chỉ để ghi lại lịch sử thay đổi.)*

## File Rename & Arrange - dùng ngay được (tính năng mới, hoàn tất 4/4 ưu tiên)

Sắp xếp thứ tự file tuỳ ý rồi copy đổi tên tuần tự (`1.ext, 2.ext...`) - giải quyết
đúng gốc rễ: hầu hết module khác của ZOLO (Draft Builder, Audio Splitter...) yêu cầu
file đặt tên đúng thứ tự số, trước đây phải tự đổi tên tay trong Explorer.

- Bấm "+ Thêm file..." (có thể bấm nhiều lần để gộp từ nhiều thư mục khác nhau).
- **Nút ↑↓ để sắp xếp lại thứ tự** trước khi đổi tên - không phụ thuộc thứ tự chọn
  file gốc trong dialog.
- Luôn **COPY** (không di chuyển/xoá file gốc) - an toàn, chạy lại nhiều lần không sợ
  mất dữ liệu nếu chọn nhầm thứ tự.
- Test qua UI thật: đổi thứ tự bằng nút ↓ (zebra↔apple), xác nhận file copy ra đúng
  theo thứ tự ĐÃ SẮP LẠI (không phải thứ tự chọn ban đầu) - kiểm tra bằng nội dung
  file thật, không chỉ tên.

## Keyframe Lab + Chọn hiệu ứng chi tiết (tính năng mới theo phản hồi)

**2 vấn đề bạn chỉ ra từ ảnh VibeCut:**

1. **"Hiệu ứng tự động" chưa có chọn chi tiết** - trước đây chỉ có checkbox bật/tắt,
   dùng bộ mặc định nhỏ (3-5 lựa chọn), không tự chọn được TÊN cụ thể như VibeCut.
2. **Draft List tự tick sẵn tất cả** - rủi ro chạy nhầm vào draft cũ không liên quan.

**Đã sửa cả 2:**

- **Draft List giờ KHÔNG tự tick** - phải chủ động chọn draft muốn thao tác, tránh
  nhầm lẫn khi có nhiều project trong cùng thư mục CapCut.
- **Bộ chọn hiệu ứng chi tiết** (nút "Chọn cụ thể ▾" cạnh mỗi loại hiệu ứng trong
  **cả Draft Builder lẫn Batch Studio** - mỗi job trong Batch Studio có pool riêng độc
  lập, không dùng chung): mở ra ô tìm kiếm + danh sách chip tên hiệu ứng thật (155
  intro, 453 transition, 1052 filter, 13 named_motion, mask...), click để chọn/bỏ chọn
  nhiều cái, bỏ trống = dùng bộ mặc định như trước. Test qua UI thật: tìm "zoom" trong
  named_motion → ra đúng 1 kết quả (`spiral_zoom`), chọn xong dựng draft → cả 2 đoạn
  đều dùng đúng preset đã chọn (không phải mặc định) - test riêng cho Batch Studio với
  preset "orbital" cũng xác nhận đúng qua JSON (property `position_x/position_y` khớp
  preset, không phải `scale` mặc định).
- **Keyframe Lab**: mở rộng từ 7 preset chuyển động cơ bản (zoom/pan/rotate đơn giản)
  lên **13 preset đặt tên phong phú** giống VibeCut - `fade_in`, `slight_rotate`,
  `ken_burns_classic`, `cinematic_push`, `dramatic_reveal`, `orbital`, `heartbeat_pulse`,
  `parallax_drift`, `spiral_zoom`, `whip_shake`, `breathing_focus`, `epicenter`,
  `tilt_shift_motion` - mỗi preset là tổ hợp NHIỀU keyframe trên nhiều thuộc tính
  (scale/position/rotation/alpha/brightness/contrast), không chỉ 2 điểm đơn giản như
  trước. Đã test: xác nhận `pyJianYingDraft` nhận nhiều keyframe/thuộc tính (trước đây
  tưởng giới hạn 2 điểm), toàn bộ 13 preset chạy đúng, số điểm keyframe ghi vào JSON
  khớp chính xác với khai báo.
- **Lưu ý:** `tilt_shift_motion` chỉ là XẤP XỈ bằng chuyển động nhẹ - `pyJianYingDraft`
  không hỗ trợ hiệu ứng mờ quang học thật (cần shader riêng của CapCut).

## Batch Studio - dùng ngay được (tính năng mới)

Chạy nhiều job dựng draft song song, mỗi job cấu hình độc lập (media/audio/hiệu ứng
riêng), giống Batch Studio của VibeCut:

- Bấm "+ Thêm job" để thêm job mới, mỗi job có thẻ riêng: tên draft, tỉ lệ khung hình,
  thư mục ảnh/video, thư mục audio, checkbox hiệu ứng riêng (Intro/Transition/Filter/
  Motion/Mask).
- Chọn số luồng song song (1-4) rồi bấm "Chạy Batch" - theo dõi trạng thái từng job
  real-time (pending/running/success/error) ngay trên thẻ.

**⚠️ Phát hiện lỗi nghiêm trọng lúc build, đã sửa:** chạy nhiều job song song ban đầu
gây **Segmentation fault** (crash cứng cả server Python, không phải lỗi bắt được) -
nguyên nhân do `pymediainfo` (thư viện đọc thời lượng media, dùng trong
`draft_builder.py`) wrap thư viện C `libmediainfo` **không an toàn khi nhiều luồng gọi
đồng thời**. Đã thêm khoá (`threading.Lock`) quanh đúng đoạn đọc media, giữ nguyên
việc chạy song song cho phần còn lại (build JSON, ghi file). Test lặp lại 3 lần liên
tiếp với 3 job song song đều thành công, không crash.

## Voice + SRT Align - dùng ngay được (tính năng mới theo yêu cầu)

**Đúng nỗi đau bạn mô tả:** TTS ngoài tạo N file voice nhỏ (1 dòng = 1 file) + đã có
SRT gốc, phải kéo tay từng đoạn khớp timeline rất lâu. Tab "Voice + SRT Align" tự
động hoá việc này:

- Chọn file SRT + thư mục voice (đặt tên `1.mp3, 2.mp3...` theo đúng thứ tự dòng SRT)
  + tuỳ chọn thêm thư mục ảnh/video nếu muốn dựng cả hình luôn.
- **2 chế độ xếp:**
  - **"Giữ nhịp gốc SRT"**: mỗi voice đặt ĐÚNG tại thời điểm SRT quy định, giữ nguyên
    độ dài thật của file voice (không ép co giãn). Sub hiển thị đúng timing gốc.
  - **"Nối liền mạch"**: bỏ qua timing gốc, voice nối tiếp nhau liên tục, sub được
    TÍNH LẠI để khớp chính xác giọng đọc thật.
- **Xử lý chồng lấn tự động:** nếu voice dài hơn khoảng cách SRT cho phép tới dòng kế
  (mode "Giữ nhịp gốc"), tool tự đẩy sang lớp audio/sub phụ (giống CapCut tự tạo track
  mới khi bạn kéo 2 đoạn đè nhau) - **không tự ý cắt ngắn giọng đọc**, chỉ báo rõ danh
  sách chỗ chồng lấn để bạn tự cân nhắc (đè nhau có thể là chủ ý, hoặc cần bạn rút gọn
  câu thoại - tool không đoán thay).
- Test thật: voice dài hơn khung SRT → tự tạo lớp phụ đúng, báo chồng lấn chính xác
  0.55s; mode nối liền mạch → voice 2 bắt đầu ngay khi voice 1 kết thúc, không lỗi.
- **Chạy được trên draft ĐÃ CÓ SẴN** (mới thêm theo yêu cầu): nếu bạn đã tự kéo ảnh/
  video/voice vào CapCut tay nhưng chưa sắp đúng timing, chọn "Dùng draft đã tick ☑"
  (tick đúng 1 draft trong Draft List trước) - tool chỉ THÊM track audio+sub mới khớp
  SRT, KHÔNG đụng nội dung/track bạn đã có sẵn. Đã test: track gốc giữ nguyên segment,
  chỉ thêm `ZOLO_voice`/`ZOLO_sub` mới bên cạnh, qua UI thật (playwright).

## Sub/Caption (Import/Export SRT) - dùng ngay được

- Tab "Sub/Caption": dùng chung danh sách draft đã tick ☑ ở khung bên trái (giống
  tab Sync). Chọn 1 thư mục chứa file SRT — **tên file phải trùng tên draft**
  (vd. draft `BL_ep01` cần file `BL_ep01.srt`) để tool tự ghép đúng cặp, tránh lẫn
  sub sai draft khi làm hàng loạt.
- **Import SRT vào draft đã tick**: draft nào không có file `.srt` khớp tên sẽ tự
  BỎ QUA (báo rõ trong log), không dừng cả batch. Import 2 lần cùng `track_name`
  vào 1 draft sẽ bị CHẶN (báo lỗi rõ ràng) — tránh tạo 2 lớp sub chồng nhau (lỗi
  này phát hiện được lúc test: bản thân thư viện không tự chặn được, ZOLO tự kiểm
  tra thêm trước khi gọi thư viện).
- **Export SRT từ draft đã tick**: lấy lại sub đã có trong draft (do tool tự import,
  hoặc do bạn tự thêm tay trong CapCut) ra file `.srt`, lưu vào
  `<Output>/exported_subs/<tên_draft>.srt` — hữu ích để review/dịch tiếp trước khi
  đưa cho team dựng phim, đúng quy trình dubbing/sub bạn đang làm.
- Cỡ chữ, `track_name` chỉnh được trực tiếp trên GUI.

## Effects/Filters/Keyframes - dùng ngay được (tích hợp vào Draft Builder)

**Phát hiện quan trọng lúc build/test:** ban đầu định làm module riêng (mở draft có
sẵn -> gắn hiệu ứng -> lưu lại), nhưng `pyJianYingDraft` mở draft có sẵn ở "template
mode" trả về segment RÚT GỌN (`ImportedMediaSegment`), không có hàm `add_animation/
add_filter/add_transition/add_keyframe` - các hàm này chỉ tồn tại trên segment MỚI
TẠO. Vậy hiệu ứng phải gắn NGAY lúc `Draft Builder` dựng từng đoạn, không tách được
thành bước riêng sau đó. Vì vậy 4 ô hiệu ứng nằm chung tab "Draft Builder":

- **Animation vào (intro)**: hiệu ứng xuất hiện đầu mỗi đoạn, lặp vòng qua 5 kiểu
  (thu nhỏ động cảm, trượt 4 hướng) để các đoạn liên tiếp không bị trùng.
- **Transition giữa các đoạn**: chuyển cảnh giữa 2 đoạn liền kề, đoạn CUỐI CÙNG
  không có (không có đoạn sau để chuyển tới) - đây là hành vi đúng, không phải lỗi.
- **Filter màu**: tắt mặc định vì dễ làm lệch tông màu ảnh gốc ngoài ý muốn, cần
  bạn chủ động bật nếu muốn.
- **Ken Burns (zoom nhẹ dần)**: rất hợp với ảnh tĩnh (BL comic, faceless content) -
  tạo cảm giác "động" dù ảnh đứng yên, xen kẽ zoom in/out giữa các đoạn cho đỡ đơn điệu.

Tên hiệu ứng trong code là tiếng Trung (gốc thư viện JianYing), nhưng **resource_id
dùng chung hệ ByteDance** nên mở trong CapCut quốc tế vẫn hiện đúng hiệu ứng - đã
verify resource_id thật ghi vào JSON khớp với dữ liệu gốc của thư viện (không phải
placeholder). Muốn đổi bộ hiệu ứng mặc định, sửa `DEFAULT_INTRO_POOL` /
`DEFAULT_TRANSITION_POOL` / `DEFAULT_FILTER_POOL` trong `effects_module.py`, dùng
hàm `list_available("intro"|"transition"|"filter")` để xem toàn bộ tên hợp lệ trước
khi thêm vào pool (đã có 1 lần chọn nhầm tên không tồn tại lúc build, giờ có sẵn hàm
`verify_pool()` tự kiểm tra và báo lỗi rõ ràng thay vì để CapCut mở lên mới phát hiện).

## Draft Builder - dùng ngay được

- Tab "Draft Builder": chọn thư mục ảnh/video (đặt tên `1.jpg, 2.jpg...` hoặc bất kỳ,
  tool tự sắp xếp theo số) + thư mục audio đã tách (từ Audio Splitter, đúng `1.mp3,
  2.mp3...`) -> ghép `media[i]` với `audio[i]` theo thứ tự, độ dài mỗi đoạn = độ dài
  audio tương ứng.
- Draft xuất thẳng vào thư mục Projects của CapCut (đường dẫn ở ô trên cùng GUI) ->
  mở CapCut lên là thấy draft mới, timeline đã sắp sẵn, chỉ cần kiểm tra + Export.
- Nếu số ảnh/video và số audio không khớp, tool chỉ ghép tới cặp cuối cùng còn đủ,
  báo cảnh báo trong log - không tự đoán/kéo dài.
- Trùng tên draft sẽ báo lỗi rõ ràng (không tự ghi đè draft cũ).

## Audio Splitter - dùng ngay được (có waveform + nghe thử trước khi cắt)

**Mới thêm:** trước đây bấm "Tách Audio" là cắt luôn theo khoảng lặng tự động, không
xem/nghe trước được - khác VibeCut. Giờ luồng đã giống VibeCut hơn nhiều:

1. Chọn file audio -> chọn mode + ngưỡng lặng như cũ (dùng để TỰ ĐỘNG phát hiện
   điểm cắt ban đầu) -> bấm "Xem trước & Tách Audio" -> tool tính waveform (dùng
   ĐÚNG kỹ thuật VibeCut dùng: ffmpeg decode PCM thô -> downsample lấy đỉnh biên độ
   - xem `audio_splitter.get_waveform_peaks()`), mở cửa sổ riêng.
2. Trong cửa sổ waveform:
   - **Kéo vạch đỏ** = dịch điểm cắt (không bị giới hạn theo khoảng lặng tự động nữa,
     toàn quyền chỉnh tay).
   - **Click vào giữa 1 đoạn** = nghe thử NGAY đoạn đó (cắt tạm bằng ffmpeg + phát
     bằng pygame, không đụng file gốc).
   - **Click chuột phải** = thêm điểm cắt mới tại vị trí đó.
   - **Double-click vạch đỏ** = xoá điểm cắt (gộp 2 đoạn liền kề).
3. Bấm "✅ Xác nhận & Tách Audio" mới thực sự cắt file, dùng ĐÚNG điểm cắt bạn vừa
   xem/chỉnh - không tính lại từ đầu.
- Kết quả xuất vào `<Output>/split_<tên file>/1.mp3, 2.mp3, ...` — đúng số thứ tự để
  bước sau (Draft Builder) ghép mỗi đoạn với 1 ảnh/video theo thứ tự.
- Cần cài thêm `pygame` (đã có trong requirements.txt) để nghe thử. Nếu máy không có
  loa/driver âm thanh, phần nghe thử báo lỗi nhẹ trong log, không crash cả tool.

## Đồng bộ âm thanh - dùng ngay được

- **Mode "Ghép theo cặp"**: dùng khi mỗi ảnh/video đi kèm 1 file voice riêng (kiểu
  Story/TikTok content). Video dài hơn voice cùng cặp -> tự cắt. Video ngắn hơn ->
  chỉ cảnh báo, không tự kéo dài (tránh giật hình ảnh tĩnh).
- **Mode "Tổng thời lượng"**: dùng khi có 1 giọng đọc dài + nhiều ảnh/video nối tiếp
  (kiểu Classic/Mixed). Cắt bớt đoạn cuối cùng cho vừa đúng tổng thời lượng voice.
- Luôn bấm **Preview** trước để xem log các thay đổi dự kiến, rồi mới **Apply**.
- Mỗi lần Apply đều tạo file backup `draft_content.json.bak.<timestamp>` cạnh file gốc.

**Cảnh báo tương thích:** một số bản CapCut/JianYing mới mã hoá `draft_content.json`.
Nếu tool báo lỗi đọc JSON ngay khi Preview, có thể draft của bạn đã bị mã hoá -
kiểm tra bằng cách mở thử file `.json` bằng Notepad, nếu thấy chữ đọc được (không
phải ký tự lạ) là chưa mã hoá, dùng tool bình thường được.

## Calibrate Auto Render (tuỳ chọn - không bắt buộc)

Toàn bộ pipeline chính (Audio Splitter -> Draft Builder + hiệu ứng -> Import Sub ->
mở CapCut Export tay) đã dùng được đầy đủ mà KHÔNG cần module này. Auto Render chỉ
cần nếu bạn muốn tool tự bấm nút Export thay bạn luôn (rủi ro cao hơn vì phải điều
khiển UI thật, xem giải thích ở đầu file).

CapCut không có API render chính thức nên module này phải điều khiển UI thật qua
`pywinauto` (bám theo TÊN nút, không phải toạ độ pixel như tool tham khảo - ổn định
hơn khi đổi màn hình/độ phân giải).

**Các bước:**

1. Mở CapCut PC, mở sẵn 1 project bất kỳ trên timeline.
2. Chạy: `python auto_render.py --discover`
3. Mở file `discover_output.txt` vừa tạo ra, tìm các dòng có chữ liên quan tới nút
   Export/Xuất (Ctrl+F "Export" hoặc "Xuất").
4. Copy đúng tên control tìm được, điền vào `CONTROL_NAMES` trong `auto_render.py`
   (đã có sẵn khung, chỉ cần sửa giá trị).
5. Nếu bước discover **không thấy control nào cả** (CapCut renderer tự vẽ, không
   expose accessibility) -> báo lại kết quả, mình sẽ chuyển sang phương án toạ độ
   tỉ lệ % (`FALLBACK_COORDINATES`) kèm code đo toạ độ tự động.
6. Test với 1 project trước khi chạy hàng loạt.

## Cấu trúc project

```
ZOLO_AutoCapCut/
├── draft_utils.py         # Đọc/ghi draft_content.json an toàn, list draft
├── audio_sync.py          # Đồng bộ âm thanh cho draft có sẵn (2 mode: pair/total)
├── audio_splitter.py      # Tách audio dài theo khoảng lặng + tính waveform (ffmpeg)
├── audio_preview.py       # Nghe thử đoạn audio trước khi cắt (pygame)
├── waveform_widget.py     # Canvas waveform tương tác (kéo/click/thêm/xoá điểm cắt)
├── draft_builder.py       # Dựng draft mới từ ảnh/video + audio (pyJianYingDraft)
├── effects_module.py      # Bộ hiệu ứng intro/transition/filter/Ken Burns (gọi từ draft_builder)
├── captions_module.py     # Import/export SRT hàng loạt
├── voice_srt_align.py      # Xếp nhiều file voice nhỏ khớp timeline theo SRT
├── batch_module.py         # Chạy nhiều job dựng draft song song (Batch Studio)
├── video_splitter.py        # Tách video theo khoảng lặng, audio-only/xoá đoạn
├── file_rename_module.py    # Sắp xếp + đổi tên file hàng loạt (1.ext, 2.ext...)
├── sticker_module.py       # Tìm + chèn sticker (search qua capcut_mate_engine cục bộ)
├── capcut_mate_engine/      # Server capcut-mate vendor (Apache 2.0) - chỉ dùng tra cứu
├── server.py               # Backend Flask cho giao diện Web (bọc API lên module trên)
├── static/                 # Frontend Web (index.html, style.css, app.js)
├── auto_render.py         # UI automation render (tuỳ chọn, cần calibrate)
├── zolo_autocapcut_gui.py # GUI tkinter (bản cũ, vẫn dùng được)
├── requirements.txt
├── setup.bat / run.bat / run_web.bat
└── README.md
```

## Quy trình làm việc đầy đủ (end-to-end)

1. **Audio Splitter**: đưa file voice dài vào, tách theo câu -> `1.mp3, 2.mp3, ...`
2. **Draft Builder**: chọn thư mục ảnh/video + thư mục audio vừa tách, bật hiệu ứng
   muốn dùng (intro/transition/Ken Burns), bấm Dựng Draft -> draft CapCut hoàn chỉnh
   xuất hiện ngay trong CapCut.
3. **Sub/Caption** (nếu có sub đã dịch): chọn thư mục SRT (tên file khớp tên draft),
   Import SRT vào draft đã tick.
4. Mở CapCut, kiểm tra lại toàn bộ, chỉnh tay nếu cần, bấm Export.
5. (Tuỳ chọn) Auto Render nếu đã calibrate xong, để tool tự bấm Export hàng loạt.
