# -*- coding: utf-8 -*-
"""
captions_module.py
Import file SRT (đã dịch sẵn - đúng quy trình dubbing/sub hiện tại của bạn) vào draft
CapCut hàng loạt, và xuất ngược lại SRT từ draft có sẵn (để review/dịch tiếp).

Khác với effects_module.py: import_srt() của pyJianYingDraft hoạt động được ở CẢ
2 chế độ (draft mới tạo lẫn draft mở lại bằng load_template) vì nó luôn tạo TextSegment
MỚI từ đầu, không sửa segment cũ - nên tách được thành module độc lập, gọi SAU khi
draft_builder.py đã dựng xong.
"""

import re
from pathlib import Path
from typing import Dict, Optional

import pyJianYingDraft as jy


def import_srt_with_animation(
    projects_root: Path,
    draft_name: str,
    srt_path: Path,
    track_name: str = "ZOLO_sub",
    font_size: float = 8.0,
    color: tuple = (1.0, 1.0, 1.0),
    bold: bool = False,
    align: int = 1,
    intro_pool: Optional[list] = None,
    intro_mode: str = "rotate",
    allow_duplicate_track: bool = False,
) -> dict:
    """
    Giống import_srt_into_draft() nhưng gắn thêm TEXT ANIMATION (intro) cho TỪNG dòng
    sub - tính năng phát hiện được từ VibeCut (add_captions.pyc có dùng TextIntro/
    TextOutro/TextLoopAnim) nhưng không có trong hàm import_srt() gốc của thư viện.

    Tự parse SRT (dùng lại đúng hàm srt_tstamp() của thư viện để parse timestamp chuẩn
    - KHÔNG tự viết lại logic parse timestamp, tránh sai lệch định dạng) thay vì gọi
    ScriptFile.import_srt() có sẵn, vì hàm gốc không cho chèn add_animation() vào giữa
    quá trình tạo từng TextSegment.
    """
    import pyJianYingDraft.time_util as time_util

    if not srt_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file SRT: {srt_path}")

    if not allow_duplicate_track:
        from draft_utils import load_draft, get_tracks
        json_path = Path(projects_root) / draft_name / "draft_content.json"
        existing_data = load_draft(json_path)
        existing_names = {t.get("name") for t in get_tracks(existing_data, "text")}
        if track_name in existing_names:
            raise NameError(
                f"Track '{track_name}' đã tồn tại trong draft '{draft_name}'. "
                f"Dùng track_name khác, hoặc allow_duplicate_track=True."
            )

    pool = intro_pool or ["渐显", "打字机_I", "波浪弹入"]
    bad = [n for n in pool if n not in {x.name for x in jy.TextIntro}]
    if bad:
        raise ValueError(f"Tên text animation không hợp lệ: {bad}")

    folder = jy.DraftFolder(str(projects_root))
    script = folder.load_template(draft_name)
    text_style = jy.TextStyle(size=font_size, color=color, bold=bold, align=align)

    # import_srt() gốc tự tạo track nếu chưa có (chèn sau track video/text cuối cùng) -
    # tự làm lại vì mình không gọi hàm gốc.
    if track_name not in script.tracks:
        script.append_track(jy.TrackSpec(jy.TrackType.text, track_name))

    # ─── Parse SRT thủ công (đúng state machine của thư viện gốc) ───
    with open(srt_path, "r", encoding="utf-8-sig") as f:
        lines = f.readlines()

    entries = []  # (text, start_us, duration_us)
    index = 0
    text_buf = ""
    trange = None
    state = "index"
    while index < len(lines):
        line = lines[index].strip()
        if state == "index":
            if not line:
                index += 1
                continue
            if not line.isdigit():
                raise ValueError(f"SRT lỗi định dạng ở dòng {index+1}: mong đợi số thứ tự, gặp '{line}'")
            index += 1
            state = "timestamp"
        elif state == "timestamp":
            start_str, end_str = line.split(" --> ")
            start, end = time_util.srt_tstamp(start_str), time_util.srt_tstamp(end_str)
            trange = jy.Timerange(start, end - start)
            index += 1
            state = "content"
        elif state == "content":
            if not line:
                entries.append((text_buf.strip(), trange))
                text_buf = ""
                state = "index"
            else:
                text_buf += line + "\n"
            index += 1
    if text_buf:
        entries.append((text_buf.strip(), trange))

    applied = []
    for i, (text, t_range) in enumerate(entries):
        seg = jy.TextSegment(text, t_range, style=text_style)
        anim_name = fx_pick(pool, intro_mode, i)
        seg.add_animation(getattr(jy.TextIntro, anim_name))
        script.add_segment(seg, track_name)
        applied.append({"text": text, "animation": anim_name})

    script.save()
    return {"draft_name": draft_name, "srt_path": str(srt_path), "track_name": track_name,
            "count": len(entries), "applied": applied}


def fx_pick(pool: list, mode: str, index: int) -> str:
    """Chọn hiệu ứng từ pool theo rotate/random (tách riêng khỏi effects_module để
    captions_module không phải import chéo effects_module chỉ vì 1 hàm nhỏ)."""
    import random
    if mode == "random":
        return random.choice(pool)
    return pool[index % len(pool)]


def import_srt_into_draft(
    projects_root: Path,
    draft_name: str,
    srt_path: Path,
    track_name: str = "ZOLO_sub",
    font_size: float = 8.0,
    color: tuple = (1.0, 1.0, 1.0),
    bold: bool = False,
    align: int = 1,  # 0=trái, 1=giữa, 2=phải
    time_offset_s: float = 0.0,
    allow_duplicate_track: bool = False,
) -> dict:
    """
    Import 1 file SRT vào 1 draft CapCut có sẵn (mở bằng template mode).

    CẢNH BÁO ĐÃ PHÁT HIỆN LÚC TEST: `ScriptFile.import_srt()` của pyJianYingDraft chỉ
    check trùng tên track trong PHIÊN LÀM VIỆC hiện tại (in-memory) - không đọc lại
    draft_content.json đã lưu từ lần chạy trước. Nghĩa là gọi hàm này 2 lần với cùng
    `track_name` cho cùng 1 draft sẽ ÂM THẦM TẠO 2 TRACK TRÙNG TÊN (2 lớp sub chồng
    nhau trong CapCut) thay vì báo lỗi như docstring gốc mô tả. Vì vậy hàm này tự đọc
    draft_content.json TRƯỚC khi gọi thư viện để chặn tình huống đó.
    """
    if not srt_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file SRT: {srt_path}")

    if not allow_duplicate_track:
        from draft_utils import load_draft, get_tracks
        json_path = Path(projects_root) / draft_name / "draft_content.json"
        existing_data = load_draft(json_path)
        existing_names = {t.get("name") for t in get_tracks(existing_data, "text")}
        if track_name in existing_names:
            raise NameError(
                f"Track '{track_name}' đã tồn tại trong draft '{draft_name}' (từ lần import "
                f"trước). Dùng track_name khác, hoặc allow_duplicate_track=True nếu CỐ Ý muốn "
                f"thêm nhiều lớp sub."
            )

    folder = jy.DraftFolder(str(projects_root))
    script = folder.load_template(draft_name)

    text_style = jy.TextStyle(size=font_size, color=color, bold=bold, align=align)

    script.import_srt(
        str(srt_path), track_name,
        time_offset=time_offset_s,
        text_style=text_style,
        # KHÔNG truyền clip_settings -> dùng mặc định của thư viện (giống CapCut tự
        # import). Đã test: truyền clip_settings=None sẽ báo lỗi vì thư viện yêu cầu
        # phải có clip_settings HOẶC style_reference, không được để trống cả hai.
    )
    script.save()

    return {"draft_name": draft_name, "srt_path": str(srt_path), "track_name": track_name}


def batch_import_srt(
    projects_root: Path,
    draft_to_srt: Dict[str, Path],
    track_name: str = "ZOLO_sub",
    **style_kwargs,
) -> dict:
    """
    Import hàng loạt: dict {tên_draft: đường_dẫn_srt}. Dùng khi bạn có N draft đã
    dựng sẵn (draft_builder.py) và N file SRT đã dịch tương ứng, ghép đúng cặp theo
    tên draft bạn tự chỉ định (an toàn hơn ghép theo thứ tự, tránh lẫn draft/sub sai cặp).

    Trả về {"success": [...], "failed": [{"draft_name", "error"}]}
    """
    results = {"success": [], "failed": []}
    for draft_name, srt_path in draft_to_srt.items():
        try:
            r = import_srt_into_draft(projects_root, draft_name, Path(srt_path),
                                       track_name=track_name, **style_kwargs)
            results["success"].append(r)
        except Exception as e:
            results["failed"].append({"draft_name": draft_name, "error": str(e)})
    return results


# ─── Chiều ngược lại: xuất sub CÓ SẴN trong draft ra file SRT ───

def _us_to_srt_timestamp(microseconds: int) -> str:
    total_ms = microseconds // 1000
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{ms:03d}"


def export_srt_from_draft(projects_root: Path, draft_name: str, output_srt_path: Path,
                           track_name: Optional[str] = None) -> dict:
    """
    Xuất ngược lại text track (sub) CÓ SẴN trong draft ra file .srt - dùng khi cần
    lấy lại sub đã chỉnh tay trong CapCut để tiếp tục dịch/review ở bước khác.

    Đọc thẳng draft_content.json (không qua pyJianYingDraft) vì chỉ cần đọc, không
    sửa - tận dụng lại draft_utils.py cho nhất quán với các module khác.
    """
    from draft_utils import load_draft, get_tracks, find_material

    json_path = Path(projects_root) / draft_name / "draft_content.json"
    data = load_draft(json_path)

    text_tracks = get_tracks(data, "text")
    if track_name:
        text_tracks = [t for t in text_tracks if t.get("name") == track_name]
    if not text_tracks:
        raise ValueError(f"Không tìm thấy track text nào trong draft '{draft_name}'"
                          + (f" (tên '{track_name}')" if track_name else ""))

    entries = []
    for track in text_tracks:
        for seg in track.get("segments", []):
            _, material = find_material(data, seg["material_id"])
            if not material:
                continue
            raw_content = material.get("content", "{}")
            try:
                import json as _json
                parsed = _json.loads(raw_content)
                text = parsed.get("text", "")
            except Exception:
                text = raw_content
            tr = seg["target_timerange"]
            entries.append({
                "start_us": tr["start"],
                "end_us": tr["start"] + tr["duration"],
                "text": text,
            })

    entries.sort(key=lambda e: e["start_us"])

    output_srt_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_srt_path, "w", encoding="utf-8") as f:
        for i, e in enumerate(entries, start=1):
            f.write(f"{i}\n")
            f.write(f"{_us_to_srt_timestamp(e['start_us'])} --> {_us_to_srt_timestamp(e['end_us'])}\n")
            f.write(f"{e['text']}\n\n")

    return {"draft_name": draft_name, "output_path": str(output_srt_path), "count": len(entries)}
