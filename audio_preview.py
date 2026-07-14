# -*- coding: utf-8 -*-
"""
audio_preview.py
Trích 1 đoạn audio ra file tạm rồi phát thử - giống tính năng "nghe thử trước khi cắt"
của VibeCut (xem nodeapi/ipcHandlers.js - extract-audio-segment handler, dùng ffmpeg
-ss/-t sau -i để seek chính xác từng sample, rồi phát bằng pygame ở phía Python thay
vì HTML5 <audio> như VibeCut).

Dùng pygame.mixer vì: nhẹ, cross-platform, hỗ trợ mp3/wav, có stop() giữa chừng
(khác winsound chỉ chơi hết bài hoặc dừng hẳn, không tiện cho việc bấm nghe-thử liên tục).
"""

import subprocess
import tempfile
from pathlib import Path
from typing import Optional

try:
    import pygame
    _PYGAME_AVAILABLE = True
except ImportError:
    _PYGAME_AVAILABLE = False

_mixer_ready = False
_temp_dir: Optional[Path] = None


def _ensure_temp_dir():
    global _temp_dir
    if _temp_dir is None:
        _temp_dir = Path(tempfile.mkdtemp(prefix="zolo_audio_preview_"))


def _ensure_mixer():
    global _mixer_ready
    if not _PYGAME_AVAILABLE:
        raise RuntimeError("Chưa cài pygame. Chạy: pip install pygame")
    if not _mixer_ready:
        pygame.mixer.init()
        _mixer_ready = True
    _ensure_temp_dir()


def extract_segment(file_path: Path, start_s: float, end_s: float) -> Path:
    """Cắt 1 đoạn ra file WAV tạm để phát thử (không đụng tới file gốc).
    Chỉ dùng ffmpeg - KHÔNG cần loa/audio device, tách riêng khỏi play()."""
    _ensure_temp_dir()
    duration = end_s - start_s
    if duration <= 0:
        raise ValueError("Đoạn nghe thử phải có độ dài > 0")

    out_path = _temp_dir / f"preview_{int(start_s*1000)}_{int(end_s*1000)}.wav"
    subprocess.run([
        "ffmpeg", "-i", str(file_path),
        "-ss", f"{start_s:.3f}", "-t", f"{duration:.3f}",
        "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
        "-y", str(out_path),
    ], capture_output=True, timeout=30, check=True)
    return out_path


def play(file_path: Path):
    """Phát 1 file audio (không chặn - trả lệnh về ngay, chạy nền)."""
    _ensure_mixer()
    pygame.mixer.music.load(str(file_path))
    pygame.mixer.music.play()


def play_segment(file_path: Path, start_s: float, end_s: float):
    """Tiện ích gộp: cắt đoạn + phát ngay."""
    seg_path = extract_segment(file_path, start_s, end_s)
    play(seg_path)
    return seg_path


def stop():
    if _PYGAME_AVAILABLE and _mixer_ready:
        pygame.mixer.music.stop()


def is_playing() -> bool:
    if not (_PYGAME_AVAILABLE and _mixer_ready):
        return False
    return pygame.mixer.music.get_busy()


def cleanup_temp_files():
    """Xoá file tạm đã tạo trong phiên làm việc (gọi lúc đóng app)."""
    if _temp_dir and _temp_dir.exists():
        for f in _temp_dir.glob("preview_*.wav"):
            try:
                f.unlink()
            except OSError:
                pass
