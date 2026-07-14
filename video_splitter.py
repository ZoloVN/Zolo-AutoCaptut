# -*- coding: utf-8 -*-
"""
video_splitter.py
Tách video dài thành nhiều đoạn theo khoảng lặng lời nói - giống "Video Splitter
(Tách nhịp)" của VibeCut. Tái dùng TOÀN BỘ logic phân tích khoảng lặng/waveform của
audio_splitter.py (ffmpeg tự tách audio từ video để phân tích - đã verify hoạt động
đúng, không cần viết lại).

Khác audio_splitter ở phần XUẤT: audio_splitter chỉ xuất audio, video_splitter xuất
VIDEO (giữ cả hình lẫn tiếng), và hỗ trợ thêm:
  - Đánh dấu đoạn "audio-only" (giữ tiếng, bỏ hình) - dùng khi muốn tự chèn B-roll
    thay cho hình gốc ở đoạn đó (footage gốc bị rung/lỗi hình nhưng tiếng vẫn ổn).
  - Xoá hẳn 1 đoạn khỏi kết quả (đoạn nói lỗi/vấp) - không xuất file cho đoạn đó.
"""

import subprocess
from pathlib import Path
from typing import List, Literal, Optional

# Tái dùng nguyên logic phân tích - không viết lại (đã test kỹ ở audio_splitter.py)
from audio_splitter import (
    Segment, get_audio_duration, analyze_silence, segments_from_silence, get_waveform_peaks,
)


def split_video(file_path: Path, segments: List[Segment], output_dir: Path,
                 audio_only_indices: Optional[List[int]] = None,
                 deleted_indices: Optional[List[int]] = None,
                 reencode: bool = True) -> List[dict]:
    """
    Cắt video thật theo danh sách segment.

    audio_only_indices: list các segment.index cần XUẤT DẠNG CHỈ CÓ TIẾNG (bỏ hình,
        đuôi .mp3) - dùng để tự chèn B-roll thay thế sau.
    deleted_indices: list các segment.index BỊ BỎ QUA HOÀN TOÀN (không xuất file) -
        đoạn nói lỗi/vấp muốn loại bỏ.
    reencode: True = re-encode (chính xác từng frame, chậm hơn); False = dùng
        "-c copy" (nhanh, không mất chất lượng, nhưng điểm cắt có thể lệch tới
        keyframe gần nhất - CapCut/video thường cần re-encode để cắt chính xác).

    Trả về list dict mô tả file đã xuất: {"index", "kind": "video"|"audio_only"|"deleted", "path"}
    """
    audio_only_indices = set(audio_only_indices or [])
    deleted_indices = set(deleted_indices or [])
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for seg in segments:
        if seg.index in deleted_indices:
            results.append({"index": seg.index, "kind": "deleted", "path": None})
            continue

        is_audio_only = seg.index in audio_only_indices
        ext = "mp3" if is_audio_only else "mp4"
        out_path = output_dir / f"{seg.index}.{ext}"

        cmd = ["ffmpeg", "-i", str(file_path), "-ss", f"{seg.start:.3f}", "-t", f"{seg.duration:.3f}"]
        if is_audio_only:
            cmd += ["-vn", "-acodec", "libmp3lame", "-q:a", "2"]
        elif reencode:
            cmd += ["-c:v", "libx264", "-preset", "fast", "-crf", "18", "-c:a", "aac"]
        else:
            cmd += ["-c", "copy"]
        cmd += ["-y", str(out_path)]

        subprocess.run(cmd, capture_output=True, timeout=120, check=True)
        results.append({
            "index": seg.index,
            "kind": "audio_only" if is_audio_only else "video",
            "path": str(out_path),
        })

    return results


def split_video_by_silence(file_path: Path, output_dir: Path,
                            silence_threshold_db: float = -35,
                            min_silence_duration: float = 0.15,
                            mode: Literal["sentence", "count"] = "sentence",
                            sentences_per_segment: int = 1,
                            target_count: int = 5,
                            audio_only_indices: Optional[List[int]] = None,
                            deleted_indices: Optional[List[int]] = None) -> dict:
    """Hàm tiện ích gộp cả pipeline: phân tích khoảng lặng -> tính segment -> cắt thật."""
    duration = get_audio_duration(file_path)
    silences = analyze_silence(file_path, silence_threshold_db, min_silence_duration)
    segments = segments_from_silence(duration, silences, mode, sentences_per_segment, target_count)
    results = split_video(file_path, segments, output_dir, audio_only_indices, deleted_indices)

    return {
        "segments": [{"index": s.index, "start": s.start, "end": s.end, "duration": s.duration} for s in segments],
        "outputs": results,
        "output_dir": str(output_dir),
    }
