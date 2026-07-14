# -*- coding: utf-8 -*-
"""
sticker_module.py
Tìm sticker theo từ khoá + chèn vào draft CapCut.

CẬP NHẬT: trước đây định gọi capcut-mate.jcaigc.cn (cloud công khai, không test được
trong sandbox). Giờ đã vendor NGUYÊN catalog sticker (59MB, config/sticker.json) và
server capcut-mate chạy CỤC BỘ trong capcut_mate_engine/ - search_sticker giờ hoàn
toàn LOCAL, không cần internet, đã test thật (xem README, tìm "爱心" ra kết quả thật
kèm sticker_id + ảnh preview).

Việc CHÈN sticker vẫn làm bằng pyJianYingDraft của chính ZOLO (không qua capcut-mate),
giữ nguyên tắc: capcut_mate_engine chỉ dùng để TRA CỨU (search/catalog), draft vẫn do
ZOLO tự quản lý trực tiếp.
"""

from pathlib import Path
from typing import List, Optional

import requests
import pyJianYingDraft as jy

CAPCUT_MATE_LOCAL_URL = "http://127.0.0.1:30000/openapi/capcut-mate/v1/search_sticker"


def search_sticker(keyword: str, timeout: int = 10) -> List[dict]:
    """
    Tìm sticker theo từ khoá qua capcut_mate_engine chạy CỤC BỘ (port 30000).
    Trả về list rút gọn {sticker_id, title, thumbnail_url} cho dễ hiển thị UI.

    Yêu cầu: capcut_mate_engine phải đang chạy (xem run_web.bat - tự khởi động cùng
    ZOLO). Nếu chưa chạy, báo lỗi rõ ràng thay vì im lặng thất bại.
    """
    try:
        resp = requests.post(CAPCUT_MATE_LOCAL_URL, json={"keyword": keyword}, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        raise RuntimeError(
            f"Không gọi được capcut_mate_engine cục bộ (port 30000): {e}\n"
            f"Kiểm tra service đã khởi động chưa - chạy run_web.bat sẽ tự bật cả 2 server, "
            f"hoặc tự chạy 'python capcut_mate_engine/main.py' để debug riêng."
        )

    items = data.get("data", [])
    results = []
    for item in items:
        sticker = item.get("sticker", {})
        results.append({
            "sticker_id": item.get("sticker_id", ""),
            "resource_id": item.get("sticker_id", ""),  # capcut-mate dùng chung sticker_id làm resource_id
            "title": item.get("title", ""),
            "thumbnail_url": sticker.get("track_thumbnail", ""),
        })
    return results


def decorate_sticker_track(script, track_name: str, resource_id: str, start_s: float,
                            end_s: float, scale: float = 1.0,
                            transform_x: float = 0.0, transform_y: float = 0.0):
    """
    Chèn 1 sticker vào draft ĐANG MỞ (script = ScriptFile, từ create_draft hoặc
    load_template) - hoàn toàn cục bộ, không gửi gì lên server ngoài.

    transform_x/y: tính theo tỉ lệ -1..1 so với tâm khung hình (0,0 = giữa màn hình),
    KHÔNG phải pixel - khác đơn vị pixel của capcut-mate API gốc, vì pyJianYingDraft
    dùng hệ toạ độ chuẩn hoá. Cần tự quy đổi nếu lấy transform_x/y từ ví dụ capcut-mate.
    """
    if track_name not in script.tracks:
        script.append_track(jy.TrackSpec(jy.TrackType.sticker, track_name))

    t_range = jy.Timerange(jy.tim(f"{start_s}s"), jy.tim(f"{end_s - start_s}s"))
    clip = jy.ClipSettings(transform_x=transform_x, transform_y=transform_y, scale_x=scale, scale_y=scale)
    seg = jy.StickerSegment(resource_id, t_range, clip_settings=clip)
    script.add_segment(seg, track_name)
    return seg


def add_sticker_to_draft(projects_root: Path, draft_name: str, resource_id: str,
                          start_s: float, end_s: float, track_name: str = "ZOLO_sticker",
                          scale: float = 1.0, transform_x: float = 0.0, transform_y: float = 0.0) -> dict:
    """Tiện ích: mở draft có sẵn, chèn 1 sticker theo resource_id đã biết, lưu lại."""
    folder = jy.DraftFolder(str(projects_root))
    script = folder.load_template(draft_name)
    decorate_sticker_track(script, track_name, resource_id, start_s, end_s, scale, transform_x, transform_y)
    script.save()
    return {"draft_name": draft_name, "resource_id": resource_id, "start_s": start_s, "end_s": end_s}
