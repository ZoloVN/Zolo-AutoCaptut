# -*- coding: utf-8 -*-
"""
audio_splitter.py
Tách 1 file audio dài (voice lồng tiếng) thành nhiều đoạn theo khoảng lặng - giống
tính năng "Audio Splitter" của VibeCut (silencedetect của ffmpeg).

Quy trình:
  1. analyze_silence()  -> chạy ffmpeg silencedetect, tìm mọi khoảng lặng
  2. segments_from_silence() -> từ khoảng lặng suy ra ranh giới câu/đoạn
  3. split_audio()       -> cắt thật bằng ffmpeg, xuất từng file mp3 đánh số 1.mp3, 2.mp3...

Dùng làm bước ĐẦU trong pipeline: 1 file voice dài -> N đoạn nhỏ -> mỗi đoạn ghép
với 1 ảnh/video trong draft CapCut (module draft_builder ở bước sau sẽ dùng kết quả này).
"""

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Literal


@dataclass
class Segment:
    index: int
    start: float   # giây
    end: float     # giây

    @property
    def duration(self) -> float:
        return self.end - self.start


def _run_ffmpeg_capture_stderr(args: List[str], timeout: int = 120) -> str:
    """Chạy ffmpeg, trả về stderr (nơi ffmpeg in log Duration/silence_start/silence_end)."""
    proc = subprocess.run(
        ["ffmpeg"] + args,
        capture_output=True, text=True, timeout=timeout,
    )
    return proc.stderr or ""


def get_waveform_peaks(file_path: Path, num_peaks: int = 800) -> List[float]:
    """
    Tính dữ liệu waveform (mảng biên độ 0..1) để vẽ lên Canvas - PORT LẠI đúng kỹ
    thuật VibeCut dùng (xem nodeapi/ipcHandlers.js - get-audio-waveform handler):
    ffmpeg decode ra PCM 16-bit mono 8kHz thô, downsample lấy giá trị đỉnh (max abs)
    mỗi cụm mẫu, chuẩn hoá về 0..1.
    """
    proc = subprocess.run(
        ["ffmpeg", "-i", str(file_path), "-ac", "1", "-ar", "8000",
         "-f", "s16le", "-acodec", "pcm_s16le", "-"],
        capture_output=True, timeout=60,
    )
    raw = proc.stdout
    if not raw:
        return []

    import struct
    n_samples = len(raw) // 2
    samples = struct.unpack(f"<{n_samples}h", raw[:n_samples * 2])

    if n_samples == 0:
        return []

    samples_per_peak = max(1, n_samples // num_peaks)
    peaks = []
    for i in range(0, n_samples, samples_per_peak):
        chunk = samples[i:i + samples_per_peak]
        if not chunk:
            continue
        peak = max(abs(s) for s in chunk) / 32768
        peaks.append(peak)
        if len(peaks) >= num_peaks:
            break

    return peaks


def get_audio_duration(file_path: Path) -> float:
    """Lấy tổng thời lượng file audio (giây) bằng ffprobe."""
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(file_path)],
        capture_output=True, text=True, timeout=30,
    )
    try:
        return float(proc.stdout.strip())
    except ValueError:
        raise RuntimeError(f"Không đọc được thời lượng file: {file_path}\n{proc.stderr}")


def analyze_silence(file_path: Path, silence_threshold_db: float = -35,
                     min_silence_duration: float = 0.15) -> List[dict]:
    """
    Chạy ffmpeg silencedetect, trả về list {"start": float, "end": float, "duration": float}
    là các khoảng LẶNG (không phải khoảng có tiếng) trong file.
    """
    stderr = _run_ffmpeg_capture_stderr([
        "-i", str(file_path),
        "-af", f"silencedetect=noise={silence_threshold_db}dB:d={min_silence_duration}",
        "-f", "null", "-",
    ])

    silences = []
    current_start = None
    for line in stderr.splitlines():
        m_start = re.search(r"silence_start:\s*([\d.]+)", line)
        m_end = re.search(r"silence_end:\s*([\d.]+)\s*\|\s*silence_duration:\s*([\d.]+)", line)
        if m_start:
            current_start = float(m_start.group(1))
        if m_end and current_start is not None:
            silences.append({
                "start": current_start,
                "end": float(m_end.group(1)),
                "duration": float(m_end.group(2)),
            })
            current_start = None
    return silences


def segments_from_silence(total_duration: float, silences: List[dict],
                           mode: Literal["sentence", "count"] = "sentence",
                           sentences_per_segment: int = 1,
                           target_count: int = 5) -> List[Segment]:
    """
    Suy ra các đoạn CÓ TIẾNG (segment) từ danh sách khoảng lặng.

    mode="sentence": mỗi khoảng lặng phát hiện được = 1 ranh giới câu. Gộp
        `sentences_per_segment` câu liên tiếp thành 1 segment.
    mode="count": chia đều thành khoảng `target_count` segment bất kể ranh giới câu
        (dùng khi audio gần như liền mạch, không có khoảng lặng rõ).
    """
    # Ranh giới câu = điểm giữa mỗi khoảng lặng (để không cắt hụt đầu/đuôi từ)
    boundaries = [0.0]
    for s in silences:
        mid = (s["start"] + s["end"]) / 2
        boundaries.append(mid)
    boundaries.append(total_duration)
    boundaries = sorted(set(boundaries))

    if mode == "count" and len(boundaries) < target_count + 1:
        # Không đủ khoảng lặng tự nhiên -> chia đều theo thời gian
        step = total_duration / target_count
        boundaries = [round(i * step, 3) for i in range(target_count)] + [total_duration]

    # Gộp N câu / segment
    raw_segments = []
    for i in range(0, len(boundaries) - 1, sentences_per_segment if mode == "sentence" else 1):
        start = boundaries[i]
        end_idx = min(i + (sentences_per_segment if mode == "sentence" else 1), len(boundaries) - 1)
        end = boundaries[end_idx]
        if end > start:
            raw_segments.append((start, end))

    segments = [Segment(index=i + 1, start=s, end=e) for i, (s, e) in enumerate(raw_segments)]
    return segments


def split_audio(file_path: Path, segments: List[Segment], output_dir: Path,
                 name_prefix: str = "") -> List[Path]:
    """
    Cắt thật file audio theo danh sách segment, xuất mp3 đánh số 1.mp3, 2.mp3...
    (giống VibeCut: output_dir/1.mp3, output_dir/2.mp3, ...)
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    out_paths = []

    for seg in segments:
        out_name = f"{name_prefix}{seg.index}.mp3"
        out_path = output_dir / out_name
        subprocess.run([
            "ffmpeg", "-i", str(file_path),
            "-ss", f"{seg.start:.3f}",
            "-t", f"{seg.duration:.3f}",
            "-c:a", "libmp3lame", "-q:a", "2",
            "-ar", "44100", "-ac", "2",
            "-y", str(out_path),
        ], capture_output=True, timeout=60, check=True)
        out_paths.append(out_path)

    return out_paths


def split_by_silence(file_path: Path, output_dir: Path,
                      silence_threshold_db: float = -35,
                      min_silence_duration: float = 0.15,
                      mode: Literal["sentence", "count"] = "sentence",
                      sentences_per_segment: int = 1,
                      target_count: int = 5) -> List[Segment]:
    """Hàm tiện ích gộp cả pipeline: phân tích -> tính segment -> cắt thật -> trả về segment đã cắt."""
    duration = get_audio_duration(file_path)
    silences = analyze_silence(file_path, silence_threshold_db, min_silence_duration)
    segments = segments_from_silence(duration, silences, mode, sentences_per_segment, target_count)
    split_audio(file_path, segments, output_dir)
    return segments
