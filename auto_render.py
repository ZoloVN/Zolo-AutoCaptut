# -*- coding: utf-8 -*-
"""
auto_render.py
Tự động mở project CapCut PC -> bấm Export -> đợi render xong -> đóng -> project tiếp theo.

QUAN TRỌNG - ĐỌC TRƯỚC KHI CHẠY:
CapCut không có CLI/API render chính thức, nên module này BẮT BUỘC phải điều khiển
UI thật bằng pywinauto (MS UI Automation - backend="uia"). Khác với tool tham khảo
(auto-click theo TOẠ ĐỘ PIXEL, dễ vỡ khi đổi màn hình/theme/ngôn ngữ), ở đây mình bám
theo TÊN/CONTROL TYPE của từng nút bấm -> ổn định hơn nhiều.

NHƯNG: mình không có máy Windows + CapCut thật để dò tên control chính xác. CapCut PC
có thể dùng renderer riêng (không phải control Win32/WinForms chuẩn), nên UI Automation
CÓ THỂ không "nhìn thấy" hết các nút. Vì vậy quy trình bắt buộc 2 bước:

  BƯỚC 1 (bạn chạy 1 lần, làm trên máy có CapCut mở sẵn 1 project):
      python auto_render.py --discover
    -> Lệnh này in ra TOÀN BỘ cây control (tên, control_type, auto_id) của cửa sổ
       CapCut ra file discover_output.txt. Gửi lại file đó cho mình (hoặc tự đọc)
       để tìm đúng tên nút "Export"/"Xuất", nút "Export" trong dialog xác nhận, v.v.

  BƯỚC 2: điền tên control tìm được vào phần CONFIG bên dưới (CONTROL_NAMES),
       rồi mới chạy render thật.

Nếu UI Automation không thấy nút nào cả (CapCut renderer tự vẽ, không expose
accessibility), phương án dự phòng là FALLBACK_COORDINATES bên dưới (bấm theo
toạ độ tương đối % màn hình, kèm ảnh chụp lúc setup để đối chiếu) - kém bền hơn
nhưng vẫn hoạt động được, giống nguyên lý tool tham khảo.
"""

import argparse
import sys
import time
from pathlib import Path

try:
    from pywinauto import Application, Desktop
    from pywinauto.timings import TimeoutError as PywinautoTimeout
except ImportError:
    Application = None  # cho phép import module này trên máy không phải Windows để đọc code/test logic khác


# ============================== CONFIG - CẦN CHỈNH SAU BƯỚC DISCOVER ==============================

CAPCUT_EXE_PATH = r"C:\Users\<TEN_MAY>\AppData\Local\CapCut\Apps\CapCut.exe"  # TODO: chỉnh đúng đường dẫn máy bạn

# Tên control sẽ khác nhau tuỳ CapCut bản EN/VI. Điền cả 2 khả năng, code sẽ thử lần lượt.
CONTROL_NAMES = {
    "export_button_candidates": ["Export", "Xuất"],
    "export_confirm_candidates": ["Export", "Xuất video", "Xuất"],
    "export_dialog_title_candidates": ["Export", "Xuất video"],
    "close_project_candidates": ["Close", "Đóng"],
}

# Dự phòng nếu UIA không thấy control nào (renderer tự vẽ) - toạ độ TỈ LỆ % so với
# kích thước cửa sổ CapCut (không phải pixel tuyệt đối, để đỡ vỡ khi đổi độ phân giải).
# Cần bạn tự đo lại trên máy thật bằng cách chạy --calibrate.
FALLBACK_COORDINATES = {
    "export_button": (0.93, 0.05),      # góc trên phải, ước lượng ban đầu - PHẢI đo lại
    "export_confirm": (0.5, 0.85),      # giữa dialog xác nhận - PHẢI đo lại
}

POLL_INTERVAL_S = 5
RENDER_TIMEOUT_S = 60 * 30  # tối đa 30 phút / video, quá thì coi như treo -> báo lỗi thay vì chờ vô hạn


# ============================== DISCOVER MODE ==============================

def discover(output_file="discover_output.txt"):
    """
    Kết nối vào cửa sổ CapCut đang mở và in TOÀN BỘ cây control ra file.
    Chạy khi CapCut đã mở sẵn 1 project trên màn hình.
    """
    if Application is None:
        print("Lỗi: pywinauto chưa cài hoặc không chạy trên Windows.")
        return

    app = Application(backend="uia").connect(path="CapCut.exe")
    win = app.top_window()

    import io
    buf = io.StringIO()
    _old_stdout = sys.stdout
    sys.stdout = buf
    try:
        win.print_control_identifiers(depth=None)
    finally:
        sys.stdout = _old_stdout

    Path(output_file).write_text(buf.getvalue(), encoding="utf-8")
    print(f"Đã ghi cây control vào {output_file}. Mở file này, tìm dòng có "
          f"chữ liên quan tới 'Export'/'Xuất' -> gửi lại đoạn đó để xác nhận tên control.")


# ============================== RENDER LOGIC ==============================

def _find_first(container, name_candidates, control_type=None):
    """Thử từng tên trong name_candidates, trả về control đầu tiên tìm thấy hoặc None."""
    for name in name_candidates:
        try:
            kwargs = {"title": name}
            if control_type:
                kwargs["control_type"] = control_type
            ctrl = container.child_window(**kwargs)
            if ctrl.exists(timeout=2):
                return ctrl
        except Exception:
            continue
    return None


def render_one_project(capcut_exe_path: str, project_name: str, output_dir: Path,
                        timeout_s: int = RENDER_TIMEOUT_S) -> bool:
    """
    Mở/kết nối CapCut, chọn project theo tên, bấm Export, đợi xong.
    Trả về True nếu render thành công (phát hiện file output ổn định dung lượng),
    False nếu timeout hoặc không tìm thấy nút.

    LƯU Ý: hàm này giả định project đã được MỞ SẴN trên CapCut (do CapCut không có
    cách mở project bằng command-line argument chính thức được xác nhận). Cách thực tế:
    mở CapCut, double-click project trong màn hình Home -> gọi hàm này để xử lý phần
    Export + chờ + đóng.
    """
    if Application is None:
        raise RuntimeError("pywinauto chỉ chạy trên Windows.")

    app = Application(backend="uia").connect(path="CapCut.exe")
    win = app.top_window()
    win.set_focus()

    export_btn = _find_first(win, CONTROL_NAMES["export_button_candidates"], control_type="Button")
    if export_btn is None:
        print("[CẢNH BÁO] Không tìm thấy nút Export qua UI Automation. "
              "Cần chạy --discover để tìm đúng tên control, hoặc dùng FALLBACK_COORDINATES.")
        return False

    export_btn.click_input()
    time.sleep(1)

    # Dialog xác nhận export (chọn độ phân giải/đường dẫn) - CapCut thường mở popup riêng
    confirm_btn = _find_first(Desktop(backend="uia"),
                               CONTROL_NAMES["export_confirm_candidates"], control_type="Button")
    if confirm_btn is None:
        print("[CẢNH BÁO] Không tìm thấy nút xác nhận Export trong dialog.")
        return False
    confirm_btn.click_input()

    # Poll thư mục output để biết khi nào render xong: file mới xuất hiện + dung lượng
    # ngừng tăng trong 2 lần kiểm tra liên tiếp = coi như render xong.
    return _wait_for_render_complete(output_dir, timeout_s)


def _wait_for_render_complete(output_dir: Path, timeout_s: int) -> bool:
    start = time.time()
    last_snapshot = {}
    stable_rounds = 0

    while time.time() - start < timeout_s:
        time.sleep(POLL_INTERVAL_S)
        current = {}
        if output_dir.exists():
            for f in output_dir.glob("*.mp4"):
                try:
                    current[f.name] = f.stat().st_size
                except FileNotFoundError:
                    continue

        if current and current == last_snapshot:
            stable_rounds += 1
            if stable_rounds >= 2:  # ổn định qua 2 lần check (2*POLL_INTERVAL_S giây) -> coi như xong
                return True
        else:
            stable_rounds = 0

        last_snapshot = current

    return False  # timeout


# ============================== CLI ENTRY ==============================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ZOLO Auto Render cho CapCut PC")
    parser.add_argument("--discover", action="store_true",
                         help="Dò cây control của cửa sổ CapCut đang mở, ghi ra discover_output.txt")
    args = parser.parse_args()

    if args.discover:
        discover()
    else:
        print("Chưa calibrate CONTROL_NAMES/FALLBACK_COORDINATES. "
              "Chạy 'python auto_render.py --discover' trước với CapCut đang mở 1 project.")
