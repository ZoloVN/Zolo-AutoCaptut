# -*- coding: utf-8 -*-
"""
voice_srt_align.py
Giải quyết đúng nỗi đau: TTS ngoài tạo ra N file voice nhỏ (1 dòng thoại = 1 file),
có sẵn 1 file SRT (script gốc, đã canh thời gian) - cần XẾP đúng từng voice vào đúng
vị trí thời gian trên timeline khớp với SRT, thay vì kéo tay từng đoạn trong CapCut.

2 CHẾ ĐỘ xếp:

  mode="srt_start" (mặc định - giữ nhịp gốc của SRT):
    Mỗi voice[i] đặt bắt đầu ĐÚNG tại thời điểm start của dòng SRT thứ i, độ dài giữ
    NGUYÊN độ dài thật của file voice (không co giãn ép theo khung SRT - vì TTS tự
    nhiên hiếm khi khớp chính xác thời lượng khung phụ đề gốc). Sub vẫn hiển thị theo
    ĐÚNG timing gốc trong SRT.
    -> Nếu voice dài hơn khoảng cách tới dòng kế tiếp, sẽ CHỒNG LẤN - tool tự phát
       hiện và báo danh sách chỗ chồng lấn để bạn biết mà chỉnh (không tự ý cắt/dịch
       vì có thể làm sai nhịp lồng tiếng đã canh).

  mode="sequential" (ưu tiên voice liền mạch, không khoảng trống/chồng lấn):
    Bỏ qua timing gốc trong SRT, xếp NỐI TIẾP LIÊN TỤC theo đúng thứ tự - voice[i+1]
    bắt đầu ngay khi voice[i] kết thúc. Sub được TÍNH LẠI thời gian để khớp CHÍNH XÁC
    với vị trí thật của từng voice (không dùng timing gốc trong SRT nữa).

Dùng khi: bạn đã có N file voice (đặt tên 1.mp3, 2.mp3... theo đúng thứ tự dòng SRT)
+ file SRT gốc. Có thể kèm thêm N ảnh/video (tuỳ chọn) để dựng draft hoàn chỉnh luôn.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Literal, Optional

import pyJianYingDraft as jy
import pyJianYingDraft.time_util as time_util

from draft_builder import list_media_files, IMAGE_EXTS, VIDEO_EXTS, AUDIO_EXTS


@dataclass
class SrtEntry:
    index: int
    start_us: int
    end_us: int
    text: str


def parse_srt(srt_path: Path) -> List[SrtEntry]:
    """Parse SRT dùng đúng srt_tstamp() gốc của pyJianYingDraft (không tự viết lại
    logic parse timestamp, tránh lệch định dạng)."""
    with open(srt_path, "r", encoding="utf-8-sig") as f:
        lines = f.readlines()

    entries = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if not line.isdigit():
            raise ValueError(f"SRT lỗi định dạng ở dòng {i+1}: mong đợi số thứ tự, gặp '{line}'")
        idx = int(line)
        i += 1
        ts_line = lines[i].strip()
        start_str, end_str = ts_line.split(" --> ")
        start_us, end_us = time_util.srt_tstamp(start_str), time_util.srt_tstamp(end_str)
        i += 1
        text_buf = []
        while i < len(lines) and lines[i].strip():
            text_buf.append(lines[i].strip())
            i += 1
        entries.append(SrtEntry(idx, start_us, end_us, "\n".join(text_buf)))
    return entries


def _pack_into_tracks(placements: List[dict]) -> List[List[dict]]:
    """
    Xếp các placement (có start_us/duration_us) vào nhiều 'làn' (track) sao cho
    KHÔNG có 2 placement chồng lấn nhau trong cùng 1 làn - giống cách CapCut tự đẩy
    lên track mới khi bạn kéo 2 đoạn đè nhau trên timeline.

    Thuật toán tham lam: với mỗi placement (đã sort theo start_us), thử lần lượt từng
    làn hiện có, đặt vào làn ĐẦU TIÊN không bị chồng; nếu không làn nào trống, mở làn mới.
    """
    lanes: List[List[dict]] = []
    for p in sorted(placements, key=lambda x: x["start_us"]):
        placed = False
        for lane in lanes:
            last = lane[-1]
            if p["start_us"] >= last["start_us"] + last["duration_us"]:
                lane.append(p)
                placed = True
                break
        if not placed:
            lanes.append([p])
    return lanes


def _detect_overlaps(placements: List[dict]) -> List[str]:
    """Kiểm tra voice[i] có kết thúc SAU khi voice[i+1] bắt đầu không (chồng lấn)."""
    warnings = []
    for i in range(len(placements) - 1):
        cur_end = placements[i]["start_us"] + placements[i]["duration_us"]
        next_start = placements[i + 1]["start_us"]
        if cur_end > next_start:
            overlap_s = (cur_end - next_start) / 1_000_000
            warnings.append(
                f"Voice #{placements[i]['index']} chồng lấn {overlap_s:.2f}s vào "
                f"voice #{placements[i+1]['index']} (voice dài hơn khoảng cách SRT cho phép)."
            )
    return warnings


def build_draft_from_srt_voices(
    projects_root: Path,
    draft_name: str,
    srt_path: Path,
    voice_folder: Path,
    media_folder: Optional[Path] = None,
    mode: Literal["srt_start", "sequential"] = "srt_start",
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    allow_replace: bool = False,
    caption_track_name: str = "ZOLO_sub",
    font_size: float = 8.0,
    use_existing_draft: bool = False,
) -> dict:
    """
    Dựng audio+caption (+video tuỳ chọn) theo timing SRT.

    use_existing_draft=False (mặc định): TẠO DRAFT MỚI (draft_name phải chưa tồn tại).
    use_existing_draft=True: MỞ DRAFT ĐÃ CÓ SẴN (vd. bạn đã tự kéo ảnh/video vào CapCut
    tay, giờ chỉ cần ZOLO thêm ĐÚNG audio+sub khớp SRT vào) - width/height/fps bị bỏ
    qua vì lấy theo draft có sẵn. CHỈ THÊM track mới (ZOLO_voice, ZOLO_sub...), không
    đụng tới segment/track đã có trong draft - an toàn với nội dung bạn đã sắp tay.

    Trả về dict: {"draft_name", "placements": [...], "overlap_warnings": [...], "warnings": [...]}
    """
    entries = parse_srt(srt_path)
    voice_files = list_media_files(voice_folder, AUDIO_EXTS)
    media_files = list_media_files(media_folder, IMAGE_EXTS | VIDEO_EXTS) if media_folder else None

    warnings = []
    n = min(len(entries), len(voice_files))
    if len(entries) != len(voice_files):
        warnings.append(
            f"Số dòng SRT ({len(entries)}) và số file voice ({len(voice_files)}) không khớp "
            f"- chỉ ghép {n} cặp đầu tiên theo thứ tự, phần dư bị bỏ qua."
        )
    if media_files is not None and len(media_files) < n:
        warnings.append(
            f"Số ảnh/video ({len(media_files)}) ít hơn số dòng ({n}) - các dòng cuối "
            f"sẽ không có hình."
        )

    folder = jy.DraftFolder(str(projects_root))
    if use_existing_draft:
        script = folder.load_template(draft_name)
    else:
        script = folder.create_draft(draft_name, width, height, fps, allow_replace=allow_replace)

    # ─── Bước 1: xác định placement (start_us, duration_us) cho từng voice ───
    placements = []
    cursor_us = 0
    for i in range(n):
        entry = entries[i]
        voice_path = voice_files[i]
        audio_material = jy.AudioMaterial(str(voice_path))
        duration_us = audio_material.duration

        if mode == "srt_start":
            start_us = entry.start_us
        else:  # sequential
            start_us = cursor_us
            cursor_us += duration_us

        placements.append({
            "index": i + 1,
            "voice_file": voice_path.name,
            "start_us": start_us,
            "duration_us": duration_us,
            "audio_material": audio_material,
            "entry": entry,
        })

    overlap_warnings = _detect_overlaps(placements) if mode == "srt_start" else []

    # ─── Bước 2: dồn placement chồng lấn (nếu có) sang nhiều track audio riêng,
    #     giống CapCut tự đẩy lên track mới khi 2 đoạn đè nhau ───
    audio_lanes = _pack_into_tracks(placements)
    audio_tracks = []
    for lane_i in range(len(audio_lanes)):
        name = "ZOLO_voice" if lane_i == 0 else f"ZOLO_voice_{lane_i+1}"
        audio_tracks.append(script.append_track(jy.TrackSpec(jy.TrackType.audio, name=name)))

    # Caption cũng có thể chồng lấn ở mode "srt_start" nếu 2 dòng SRT gốc đè nhau -
    # dùng CHÍNH placement (start_us đã xác định) để đảm bảo audio/sub luôn cùng làn.
    text_lanes_source = audio_lanes  # cùng cấu trúc làn với audio để dễ đối chiếu
    text_tracks = []
    for lane_i in range(len(text_lanes_source)):
        name = caption_track_name if lane_i == 0 else f"{caption_track_name}_{lane_i+1}"
        text_tracks.append(script.append_track(jy.TrackSpec(jy.TrackType.text, name=name)))

    video_track = None
    if media_files:
        video_track = script.append_track(jy.TrackSpec(jy.TrackType.video, name="ZOLO_video"))

    text_style = jy.TextStyle(size=font_size, color=(1.0, 1.0, 1.0), align=1)

    # ─── Bước 3: ghi thật vào draft, theo đúng làn đã xếp ───
    summary = []
    for lane_i, lane in enumerate(audio_lanes):
        for p in lane:
            target_range = jy.Timerange(p["start_us"], p["duration_us"])

            audio_segment = jy.AudioSegment(p["audio_material"], target_range)
            script.add_segment(audio_segment, audio_tracks[lane_i])

            if mode == "srt_start":
                cap_range = jy.Timerange(p["entry"].start_us, p["entry"].end_us - p["entry"].start_us)
            else:
                cap_range = target_range
            text_seg = jy.TextSegment(p["entry"].text, cap_range, style=text_style)
            script.add_segment(text_seg, text_tracks[lane_i])

            i = p["index"] - 1
            if media_files and i < len(media_files):
                media_material = jy.VideoMaterial(str(media_files[i]))
                video_segment = jy.VideoSegment(media_material, target_range)
                script.add_segment(video_segment, video_track)

            summary.append({
                "index": p["index"],
                "voice_file": p["voice_file"],
                "start_s": p["start_us"] / 1_000_000,
                "duration_s": p["duration_us"] / 1_000_000,
                "lane": lane_i + 1,
                "text": p["entry"].text[:40],
            })

    summary.sort(key=lambda s: s["index"])
    script.save()

    return {
        "draft_name": draft_name,
        "mode": mode,
        "placements": summary,
        "lanes_used": len(audio_lanes),
        "overlap_warnings": overlap_warnings,
        "warnings": warnings,
    }
