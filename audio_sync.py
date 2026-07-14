# -*- coding: utf-8 -*-
"""
audio_sync.py
Đồng bộ độ dài video/ảnh theo audio (giống checkbox "Cắt video nếu dài hơn âm thanh"
trong tool tham khảo).

Có 2 chế độ ghép cặp (giống 3 mode Classic/Story/Mixed của Auto CapCut Pro):

  MODE "pair"  : segment video thứ i khớp với segment audio thứ i (theo thứ tự
                 xuất hiện trên timeline). Dùng khi mỗi ảnh/video đi kèm 1 file
                 voice riêng (kiểu Story: toplist, TikTok content).
                 -> Nếu segment video dài hơn audio cùng cặp: cắt video bằng audio.
                 -> Nếu ảnh/video ngắn hơn audio cùng cặp: KHÔNG tự kéo dài (an toàn),
                    chỉ cảnh báo, để bạn tự quyết (tránh giật hình nếu kéo dài ảnh tĩnh).

  MODE "total" : coi audio track là 1 (hoặc nhiều) đoạn lồng tiếng tổng, video track
                 là nhiều đoạn ảnh/video nối tiếp. Cắt bớt đoạn CUỐI CÙNG của video
                 track cho vừa đúng tổng thời lượng audio track (kiểu Classic/Mixed:
                 1 voice dài + nhiều ảnh/video nối tiếp).

Mọi thao tác đều là DRY-RUN mặc định: trả về danh sách thay đổi dự kiến, KHÔNG ghi
file cho tới khi gọi apply=True. Luôn backup trước khi ghi (xem draft_utils.save_draft).
"""

from dataclasses import dataclass
from typing import List, Literal

from draft_utils import (
    get_tracks, find_material, save_draft, load_draft, us_to_s, s_to_us
)


@dataclass
class SyncChange:
    track_id: str
    segment_id: str
    segment_index: int
    old_duration_s: float
    new_duration_s: float
    reason: str


def _video_segments(data: dict):
    """Trả về list (track, segment) cho mọi track type=video, sắp theo target_timerange.start."""
    out = []
    for track in get_tracks(data, "video"):
        for seg in track.get("segments", []):
            out.append((track, seg))
    out.sort(key=lambda ts: ts[1]["target_timerange"]["start"])
    return out


def _audio_segments(data: dict):
    out = []
    for track in get_tracks(data, "audio"):
        for seg in track.get("segments", []):
            out.append((track, seg))
    out.sort(key=lambda ts: ts[1]["target_timerange"]["start"])
    return out


def analyze_pair_mode(data: dict) -> List[SyncChange]:
    """MODE 'pair': ghép video[i] với audio[i] theo thứ tự. Chỉ đề xuất CẮT (không kéo dài)."""
    changes = []
    videos = _video_segments(data)
    audios = _audio_segments(data)

    n = min(len(videos), len(audios))
    if len(videos) != len(audios):
        # Không raise lỗi -- vẫn xử lý phần ghép được, phần dư sẽ không đụng tới.
        pass

    for i in range(n):
        v_track, v_seg = videos[i]
        _, a_seg = audios[i]

        v_dur = v_seg["target_timerange"]["duration"]
        a_dur = a_seg["target_timerange"]["duration"]

        if v_dur > a_dur:
            changes.append(SyncChange(
                track_id=v_track["id"],
                segment_id=v_seg["id"],
                segment_index=i,
                old_duration_s=us_to_s(v_dur),
                new_duration_s=us_to_s(a_dur),
                reason=f"Video #{i+1} dài {us_to_s(v_dur):.2f}s > audio {us_to_s(a_dur):.2f}s -> cắt",
            ))
        elif v_dur < a_dur:
            changes.append(SyncChange(
                track_id=v_track["id"],
                segment_id=v_seg["id"],
                segment_index=i,
                old_duration_s=us_to_s(v_dur),
                new_duration_s=us_to_s(v_dur),  # không đổi, chỉ cảnh báo
                reason=f"CẢNH BÁO: Video #{i+1} ngắn hơn audio ({us_to_s(v_dur):.2f}s < "
                       f"{us_to_s(a_dur):.2f}s) - không tự kéo dài, cần bạn thêm media",
            ))
    return changes


def analyze_total_mode(data: dict) -> List[SyncChange]:
    """MODE 'total': cắt bớt đoạn video CUỐI cùng cho vừa tổng thời lượng audio."""
    changes = []
    videos = _video_segments(data)
    audios = _audio_segments(data)
    if not videos or not audios:
        return changes

    total_audio_end = max(a["target_timerange"]["start"] + a["target_timerange"]["duration"]
                           for _, a in audios)
    total_video_end = max(v["target_timerange"]["start"] + v["target_timerange"]["duration"]
                           for _, v in videos)

    if total_video_end <= total_audio_end:
        return changes  # video đã ngắn hơn hoặc bằng audio, không cần cắt

    # Cắt lần lượt từ đoạn cuối cùng vào, vì có thể 1 đoạn không đủ để cắt hết phần dư
    overflow = total_video_end - total_audio_end
    videos_by_end = sorted(videos, key=lambda ts: ts[1]["target_timerange"]["start"], reverse=True)

    for track, seg in videos_by_end:
        if overflow <= 0:
            break
        dur = seg["target_timerange"]["duration"]
        cut = min(overflow, dur)
        new_dur = dur - cut
        changes.append(SyncChange(
            track_id=track["id"],
            segment_id=seg["id"],
            segment_index=-1,
            old_duration_s=us_to_s(dur),
            new_duration_s=us_to_s(new_dur),
            reason=f"Cắt {us_to_s(cut):.2f}s khỏi đoạn cuối để khớp tổng audio",
        ))
        overflow -= cut
    return changes


def apply_changes(data: dict, changes: List[SyncChange], ripple: bool = True):
    """
    Ghi các thay đổi vào data (in-place). Trims cả target_timerange VÀ source_timerange
    (giữ nguyên điểm start của source, chỉ giảm duration - tức là giữ đầu clip, cắt đuôi).

    ripple=True (mặc định, BẮT BUỘC nên bật): sau khi cắt 1 segment, mọi segment
    có target_timerange.start >= điểm kết thúc CŨ của segment đó, trên MỌI track
    (video, audio, text, sticker...) sẽ bị dịch sớm lên đúng bằng khoảng đã cắt.
    Nếu không ripple, sẽ để lại khoảng trống (đứng hình / im lặng) trên timeline.
    """
    seg_by_id = {}
    all_segments_flat = []  # (track, seg) để ripple xuyên suốt mọi track
    for track in data.get("tracks", []):
        for seg in track.get("segments", []):
            seg_by_id[seg["id"]] = seg
            all_segments_flat.append((track, seg))

    applied = []
    # Xử lý theo thứ tự thời gian xuất hiện trên timeline (start tăng dần) để ripple
    # dồn đúng, tránh dịch chồng lên nhau khi có nhiều thay đổi liên tiếp.
    changes_sorted = sorted(
        [c for c in changes if c.old_duration_s != c.new_duration_s],
        key=lambda c: seg_by_id[c.segment_id]["target_timerange"]["start"]
        if c.segment_id in seg_by_id else 0,
    )

    for ch in changes_sorted:
        seg = seg_by_id.get(ch.segment_id)
        if not seg:
            continue

        old_dur_us = seg["target_timerange"]["duration"]
        new_dur_us = s_to_us(ch.new_duration_s)
        cut_amount = old_dur_us - new_dur_us
        if cut_amount <= 0:
            continue

        old_end = seg["target_timerange"]["start"] + old_dur_us

        seg["target_timerange"]["duration"] = new_dur_us
        if "source_timerange" in seg and seg["source_timerange"]:
            seg["source_timerange"]["duration"] = new_dur_us

        if ripple:
            for _, other_seg in all_segments_flat:
                if other_seg is seg:
                    continue
                other_start = other_seg["target_timerange"]["start"]
                if other_start >= old_end:
                    other_seg["target_timerange"]["start"] = other_start - cut_amount

        applied.append(ch)

    # Dọn dẹp: segment bị cắt về 0 giây sẽ làm CapCut lỗi khi mở lại project -> xoá hẳn
    for track in data.get("tracks", []):
        track["segments"] = [
            seg for seg in track.get("segments", [])
            if seg["target_timerange"]["duration"] > 0
        ]

    # Cập nhật lại duration tổng của cả project cho khớp track dài nhất
    max_end = 0
    for track in data.get("tracks", []):
        for seg in track.get("segments", []):
            end = seg["target_timerange"]["start"] + seg["target_timerange"]["duration"]
            max_end = max(max_end, end)
    if max_end > 0:
        data["duration"] = max_end

    return applied


def sync_draft(json_path, mode: Literal["pair", "total"] = "pair", apply: bool = False):
    """
    Hàm tiện ích chính: đọc draft, phân tích, (tuỳ chọn) ghi lại.
    Trả về (changes, data) để GUI hiển thị preview trước khi hỏi xác nhận ghi.
    """
    data = load_draft(json_path)
    if mode == "pair":
        changes = analyze_pair_mode(data)
    elif mode == "total":
        changes = analyze_total_mode(data)
    else:
        raise ValueError(f"Mode không hợp lệ: {mode}")

    if apply:
        applied = apply_changes(data, changes)
        if applied:
            save_draft(json_path, data, backup=True)
        return changes, data

    return changes, data
