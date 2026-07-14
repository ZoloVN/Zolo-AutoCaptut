# -*- coding: utf-8 -*-
"""
draft_utils.py
Lõi đọc/ghi draft_content.json của CapCut PC.
Không phụ thuộc UI, dùng chung cho mọi module (sync âm thanh, hiệu ứng, keyframe...).

CapCut lưu mỗi project (draft) trong 1 thư mục riêng dưới:
  Windows: C:\\Users\\<user>\\AppData\\Local\\CapCut\\User Data\\Projects\\com.lveditor.draft\\<draft_id>\\draft_content.json

Cấu trúc chính (rút gọn từ schema thực tế):
{
  "duration": <microseconds>,
  "fps": 30,
  "tracks": [
      {"id": "...", "type": "video"|"audio"|"text"|"sticker"|"effect", "segments": [...]}
  ],
  "materials": {
      "videos": [...],   # video file VÀ ảnh tĩnh (phân biệt bằng field "type": "video"/"photo")
      "audios": [...],
      "texts": [...],
      ...
  }
}

Segment quan trọng có 4 field:
  material_id       -> trỏ tới materials.<loại>[].id  (segment LÀ cái gì)
  target_timerange   -> {start, duration} vị trí trên timeline (micro giây)
  source_timerange   -> {start, duration} đoạn cắt trong file gốc (micro giây)
  extra_material_refs -> UUID tới các material đi kèm (speed, mask, animation, transition, audio_fade)

CẢNH BÁO: CapCut/JianYing bản mới (JianYing 6.0+, một số bản CapCut) có thể MÃ HOÁ
draft_content.json. Nếu load_draft() báo lỗi JSONDecodeError ngay từ đầu file,
khả năng cao là draft đã bị mã hoá -> tool này KHÔNG xử lý được, cần bản CapCut cũ hơn
hoặc chờ giải pháp giải mã riêng.
"""

import json
import os
import shutil
import time
from pathlib import Path

MICRO = 1_000_000  # 1 giây = 1,000,000 microseconds


def default_projects_root() -> Path:
    """Đường dẫn mặc định chứa toàn bộ draft trên Windows."""
    local = os.environ.get("LOCALAPPDATA", "")
    return Path(local) / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"


def list_drafts(projects_root: Path):
    """
    Trả về list dict: {"name": <tên hiển thị>, "path": <Path tới thư mục draft>,
                        "json_path": <Path tới draft_content.json>, "modified": <timestamp>}
    Bỏ qua thư mục không có draft_content.json (draft rác/lỗi).
    """
    results = []
    if not projects_root.exists():
        return results

    for entry in projects_root.iterdir():
        if not entry.is_dir():
            continue
        json_path = entry / "draft_content.json"
        if not json_path.exists():
            continue
        # Tên hiển thị: CapCut lưu tên thật trong draft_meta_info.json nếu có
        display_name = entry.name
        meta_path = entry / "draft_meta_info.json"
        if meta_path.exists():
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                name_from_meta = meta.get("draft_name", "").strip()
                if name_from_meta:
                    display_name = name_from_meta
            except Exception:
                pass
        results.append({
            "name": display_name,
            "path": entry,
            "json_path": json_path,
            "modified": json_path.stat().st_mtime,
        })
    results.sort(key=lambda d: d["modified"], reverse=True)
    return results


def load_draft(json_path: Path):
    """Đọc draft_content.json. Raise JSONDecodeError nếu bị mã hoá/hỏng."""
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_draft(json_path: Path, data: dict, backup: bool = True):
    """
    Ghi lại draft_content.json.
    LUÔN backup bản gốc trước khi ghi đè (đuôi .bak.<timestamp>), vì hỏng file này
    là mất luôn project trong CapCut (không có undo ở mức file).
    """
    if backup:
        ts = int(time.time())
        backup_path = json_path.with_suffix(f".json.bak.{ts}")
        shutil.copy2(json_path, backup_path)

    tmp_path = json_path.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp_path, json_path)  # atomic trên cùng ổ đĩa


def find_material(data: dict, material_id: str):
    """Tìm material theo id trong TẤT CẢ danh mục materials.*, trả về (category, material_dict)."""
    materials = data.get("materials", {})
    for category, items in materials.items():
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and item.get("id") == material_id:
                return category, item
    return None, None


def get_track(data: dict, track_type: str):
    """Trả về track đầu tiên khớp type (video/audio/text/...), hoặc None."""
    for track in data.get("tracks", []):
        if track.get("type") == track_type:
            return track
    return None


def get_tracks(data: dict, track_type: str):
    """Trả về TẤT CẢ track khớp type (project có thể có nhiều track video/audio chồng lớp)."""
    return [t for t in data.get("tracks", []) if t.get("type") == track_type]


def us_to_s(microseconds: int) -> float:
    return microseconds / MICRO


def s_to_us(seconds: float) -> int:
    return int(round(seconds * MICRO))
