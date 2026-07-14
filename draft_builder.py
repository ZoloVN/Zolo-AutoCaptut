# -*- coding: utf-8 -*-
"""
draft_builder.py
Dựng 1 project CapCut HOÀN CHỈNH từ:
  - 1 danh sách ảnh/video (đã sắp thứ tự)
  - 1 danh sách audio đã tách theo câu (từ audio_splitter.py, đánh số 1.mp3, 2.mp3...)

Ghép theo thứ tự: media[i] <-> audio[i], y hệt mode "Ghép theo cặp" của audio_sync.py
(Story/TikTok content: mỗi ảnh/video đi kèm 1 câu voice riêng).

Dùng pyJianYingDraft làm nền (xem README - đã xác nhận đây là thư viện các tool thương
mại như VibeCut cũng dùng). Sau khi build xong, project xuất hiện NGAY trong danh sách
draft khi mở CapCut - bạn chỉ cần mở lên xem lại + Export tay.

Cài đặt: pip install pyJianYingDraft (kéo theo pymediainfo - đọc thời lượng media,
đã bundle sẵn thư viện đọc media, không cần cài thêm gì trên Windows).
"""

from pathlib import Path
from typing import List, Optional

import threading

import pyJianYingDraft as jy
import effects_module as fx

# pymediainfo (dùng bên trong VideoMaterial/AudioMaterial để đọc duration/kích thước)
# wrap thư viện C libmediainfo - KHÔNG an toàn khi nhiều luồng cùng gọi đồng thời.
# Phát hiện lúc test Batch Studio: chạy 3 job song song không khoá -> Segmentation
# fault (Python interpreter crash cứng, không phải exception bắt được). Lock này chỉ
# khoá đúng đoạn đọc media (nhanh), phần còn lại (build JSON, ghi file) vẫn chạy song
# song bình thường giữa các luồng.
_media_probe_lock = threading.Lock()

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac"}


def _natural_sort_key(path: Path):
    """Sắp xếp '2.mp3' trước '10.mp3' (sort tự nhiên theo số, không phải theo chữ)."""
    import re
    parts = re.split(r"(\d+)", path.stem)
    return [int(p) if p.isdigit() else p for p in parts]


def list_media_files(folder: Path, exts: set) -> List[Path]:
    """Liệt kê file trong thư mục theo đúng phần mở rộng, sắp xếp tự nhiên theo số thứ tự."""
    files = [f for f in folder.iterdir() if f.suffix.lower() in exts]
    files.sort(key=_natural_sort_key)
    return files


def build_draft_from_pairs(
    projects_root: Path,
    draft_name: str,
    media_files: List[Path],
    audio_files: List[Path],
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    allow_replace: bool = False,
    # ── Tuỳ chọn hiệu ứng - áp NGAY lúc dựng segment (xem effects_module.py để hiểu
    #    vì sao không thể gắn sau khi draft đã lưu) ──
    apply_intro: bool = False,
    intro_pool: Optional[List[str]] = None,
    intro_mode: str = "rotate",
    apply_transition: bool = False,
    transition_pool: Optional[List[str]] = None,
    transition_mode: str = "rotate",
    apply_filter: bool = False,
    filter_pool: Optional[List[str]] = None,
    filter_mode: str = "rotate",
    apply_ken_burns: bool = False,
    ken_burns_zoom: float = 1.15,
    apply_motion: bool = False,
    motion_pool: Optional[List[str]] = None,
    motion_mode: str = "rotate",
    apply_named_motion: bool = False,
    named_motion_pool: Optional[List[str]] = None,
    named_motion_mode: str = "rotate",
    apply_mask: bool = False,
    mask_pool: Optional[List[str]] = None,
    mask_mode: str = "rotate",
) -> dict:
    """
    Dựng draft: media[i] ghép với audio[i] theo thứ tự, độ dài mỗi đoạn video = độ dài
    audio tương ứng (giống mode "pair" của audio_sync.py, nhưng dựng MỚI thay vì sửa
    project có sẵn).

    Trả về dict tóm tắt: {"draft_name", "segments": [...], "total_duration_s", "warnings": [...]}
    """
    if not media_files or not audio_files:
        raise ValueError("Cần ít nhất 1 media và 1 audio để dựng draft.")

    warnings = []
    n = min(len(media_files), len(audio_files))
    if len(media_files) != len(audio_files):
        warnings.append(
            f"Số lượng media ({len(media_files)}) và audio ({len(audio_files)}) không khớp "
            f"- chỉ ghép {n} cặp đầu tiên, phần dư bị bỏ qua."
        )

    if apply_intro:
        bad = fx.verify_pool("intro", intro_pool or fx.DEFAULT_INTRO_POOL)
        if bad:
            raise ValueError(f"Tên hiệu ứng intro không hợp lệ: {bad}")
    if apply_transition:
        bad = fx.verify_pool("transition", transition_pool or fx.DEFAULT_TRANSITION_POOL)
        if bad:
            raise ValueError(f"Tên transition không hợp lệ: {bad}")
    if apply_filter:
        bad = fx.verify_pool("filter", filter_pool or fx.DEFAULT_FILTER_POOL)
        if bad:
            raise ValueError(f"Tên filter không hợp lệ: {bad}")
    if apply_mask:
        bad = fx.verify_pool("mask", mask_pool or fx.DEFAULT_MASK_POOL)
        if bad:
            raise ValueError(f"Tên mask không hợp lệ: {bad}")
    if apply_motion:
        bad_presets = [p for p in (motion_pool or fx.MOTION_PRESETS) if p not in fx.MOTION_PRESETS]
        if bad_presets:
            raise ValueError(f"Preset chuyển động không hợp lệ: {bad_presets}. Chọn trong {fx.MOTION_PRESETS}")
    if apply_motion and apply_ken_burns:
        raise ValueError("Chỉ bật MỘT trong hai: apply_motion (đa dạng) hoặc apply_ken_burns (đơn giản), "
                          "tránh xung đột keyframe cùng thuộc tính.")
    if apply_named_motion:
        valid_names = set(fx.NAMED_MOTION_PRESETS.keys())
        bad_presets = [p for p in (named_motion_pool or list(valid_names)) if p not in valid_names]
        if bad_presets:
            raise ValueError(f"Preset named_motion không hợp lệ: {bad_presets}. Chọn trong {list(valid_names)}")
    if sum([apply_motion, apply_ken_burns, apply_named_motion]) > 1:
        raise ValueError("Chỉ bật MỘT trong ba: apply_motion / apply_ken_burns / apply_named_motion, "
                          "tránh xung đột keyframe cùng thuộc tính (vd 2 preset cùng gắn uniform_scale).")

    folder = jy.DraftFolder(str(projects_root))
    script = folder.create_draft(draft_name, width, height, fps, allow_replace=allow_replace)

    video_track = script.append_track(jy.TrackSpec(jy.TrackType.video, name="ZOLO_video"))
    audio_track = script.append_track(jy.TrackSpec(jy.TrackType.audio, name="ZOLO_audio"))

    cursor_us = 0
    segments_summary = []

    for i in range(n):
        media_path = media_files[i]
        audio_path = audio_files[i]

        with _media_probe_lock:
            audio_material = jy.AudioMaterial(str(audio_path))
        audio_duration_us = audio_material.duration  # micro giây, đã đọc thật từ file

        target_range = jy.Timerange(cursor_us, audio_duration_us)

        with _media_probe_lock:
            video_material = jy.VideoMaterial(str(media_path))
        video_segment = jy.VideoSegment(video_material, target_range)

        effects_applied = []
        if apply_intro:
            name = fx.pick_from_pool(intro_pool or fx.DEFAULT_INTRO_POOL, intro_mode, i)
            fx.decorate_intro(video_segment, name)
            effects_applied.append(f"intro={name}")
        if apply_transition and i < n - 1:  # đoạn cuối không có transition (không có đoạn sau)
            name = fx.pick_from_pool(transition_pool or fx.DEFAULT_TRANSITION_POOL, transition_mode, i)
            fx.decorate_transition(video_segment, name)
            effects_applied.append(f"transition={name}")
        if apply_filter:
            name = fx.pick_from_pool(filter_pool or fx.DEFAULT_FILTER_POOL, filter_mode, i)
            fx.decorate_filter(video_segment, name)
            effects_applied.append(f"filter={name}")
        if apply_ken_burns:
            zoom_from, zoom_to = (ken_burns_zoom, 1.0) if i % 2 == 1 else (1.0, ken_burns_zoom)
            fx.decorate_ken_burns(video_segment, zoom_from, zoom_to)
            effects_applied.append(f"ken_burns={zoom_from}->{zoom_to}")
        if apply_motion:
            preset = fx.pick_from_pool(motion_pool or fx.MOTION_PRESETS, motion_mode, i)
            fx.decorate_motion(video_segment, preset)
            effects_applied.append(f"motion={preset}")
        if apply_named_motion:
            preset = fx.pick_from_pool(named_motion_pool or list(fx.NAMED_MOTION_PRESETS.keys()), named_motion_mode, i)
            fx.apply_named_motion(video_segment, preset)
            effects_applied.append(f"named_motion={preset}")
        if apply_mask:
            name = fx.pick_from_pool(mask_pool or fx.DEFAULT_MASK_POOL, mask_mode, i)
            fx.decorate_mask(video_segment, name)
            effects_applied.append(f"mask={name}")

        script.add_segment(video_segment, video_track)

        audio_segment = jy.AudioSegment(audio_material, target_range)
        script.add_segment(audio_segment, audio_track)

        segments_summary.append({
            "index": i + 1,
            "media": media_path.name,
            "audio": audio_path.name,
            "start_s": cursor_us / 1_000_000,
            "duration_s": audio_duration_us / 1_000_000,
            "effects": effects_applied,
        })

        cursor_us += audio_duration_us

    script.save()

    return {
        "draft_name": draft_name,
        "segments": segments_summary,
        "total_duration_s": cursor_us / 1_000_000,
        "warnings": warnings,
        "draft_path": str(Path(projects_root) / draft_name),
    }


def build_draft_from_folders(
    projects_root: Path,
    draft_name: str,
    media_folder: Path,
    audio_folder: Path,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    allow_replace: bool = False,
    **effect_kwargs,
) -> dict:
    """Tiện ích: tự liệt kê file trong 2 thư mục (ảnh/video + audio đã tách) rồi dựng draft.
    effect_kwargs: xem build_draft_from_pairs (apply_intro, apply_transition, apply_filter,
    apply_ken_burns và các pool/mode đi kèm)."""
    media_files = list_media_files(media_folder, IMAGE_EXTS | VIDEO_EXTS)
    audio_files = list_media_files(audio_folder, AUDIO_EXTS)
    return build_draft_from_pairs(
        projects_root, draft_name, media_files, audio_files, width, height, fps, allow_replace,
        **effect_kwargs,
    )
