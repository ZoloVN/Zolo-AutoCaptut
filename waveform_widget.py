# -*- coding: utf-8 -*-
"""
waveform_widget.py
Widget tkinter Canvas vẽ waveform + ranh giới đoạn (boundary) có thể KÉO CHỈNH bằng
chuột, giống trải nghiệm waveform editor của VibeCut (nhưng vẽ bằng Canvas thay vì
HTML5 canvas, và kéo boundary bằng bind mouse thay vì JS drag).

Tương tác:
  - Kéo đường ranh giới màu đỏ để chỉnh lại điểm cắt (không giới hạn theo khoảng lặng
    tự động nữa - người dùng có toàn quyền tinh chỉnh).
  - Click (không phải kéo) vào giữa 1 đoạn -> gọi callback on_segment_click(index)
    để phần ứng dụng chính tự quyết định phát thử đoạn đó (widget không tự phát âm
    thanh, giữ tách biệt trách nhiệm - dễ test hơn).
  - Double-click ranh giới -> callback on_boundary_delete(index) để xoá điểm cắt đó
    (gộp 2 đoạn liền kề thành 1).
  - Click chuột phải lên waveform -> callback on_boundary_add(time_s) để thêm điểm
    cắt mới tại vị trí đó.
"""

import tkinter as tk
from typing import Callable, List, Optional


class WaveformEditor(tk.Frame):
    def __init__(self, parent, peaks: List[float], total_duration: float,
                 boundaries: List[float],
                 on_segment_click: Optional[Callable[[int], None]] = None,
                 on_boundaries_changed: Optional[Callable[[List[float]], None]] = None,
                 height: int = 120, bg_color: str = "white",
                 wave_color: str = "#4a90d9", boundary_color: str = "#d94a4a",
                 **kwargs):
        """
        peaks: mảng biên độ 0..1 (từ audio_splitter.get_waveform_peaks)
        total_duration: tổng thời lượng file (giây)
        boundaries: danh sách thời điểm cắt BAN ĐẦU (giây), KHÔNG bao gồm 0 và total_duration
                    (widget tự thêm 2 mốc đầu/cuối vào danh sách hiển thị)
        """
        super().__init__(parent, **kwargs)
        self.peaks = peaks
        self.total_duration = total_duration
        self.boundaries = sorted(boundaries)  # không tính điểm 0 và cuối
        self.on_segment_click = on_segment_click
        self.on_boundaries_changed = on_boundaries_changed
        self.bg_color = bg_color
        self.wave_color = wave_color
        self.boundary_color = boundary_color

        self.canvas = tk.Canvas(self, height=height, bg=bg_color, highlightthickness=1,
                                 highlightbackground="black")
        self.canvas.pack(fill="both", expand=True)

        self._dragging_index: Optional[int] = None
        self._drag_start_x: Optional[int] = None
        self._canvas_width = 1  # cập nhật thật ở lần vẽ đầu

        self.canvas.bind("<Configure>", self._on_resize)
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Double-Button-1>", self._on_double_click)
        self.canvas.bind("<Button-3>", self._on_right_click)

    # ---------------------------------------------------------------- toạ độ <-> thời gian
    def _x_to_time(self, x: int) -> float:
        w = max(1, self.canvas.winfo_width())
        return max(0.0, min(self.total_duration, (x / w) * self.total_duration))

    def _time_to_x(self, t: float) -> int:
        w = max(1, self.canvas.winfo_width())
        return int((t / self.total_duration) * w) if self.total_duration > 0 else 0

    # ---------------------------------------------------------------- vẽ
    def _on_resize(self, event=None):
        self.redraw()

    def redraw(self):
        self.canvas.delete("all")
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w <= 1 or h <= 1 or not self.peaks:
            return

        mid_y = h / 2
        bar_width = max(1, w / len(self.peaks))
        for i, peak in enumerate(self.peaks):
            x = i * bar_width
            bar_h = max(1, peak * (h / 2 - 4))
            self.canvas.create_line(x, mid_y - bar_h, x, mid_y + bar_h,
                                     fill=self.wave_color, width=max(1, bar_width))

        for i, t in enumerate(self.boundaries):
            x = self._time_to_x(t)
            self.canvas.create_line(x, 0, x, h, fill=self.boundary_color, width=2,
                                     tags=(f"boundary_{i}",))

    # ---------------------------------------------------------------- tương tác chuột
    def _hit_test_boundary(self, x: int, tolerance: int = 6) -> Optional[int]:
        for i, t in enumerate(self.boundaries):
            bx = self._time_to_x(t)
            if abs(bx - x) <= tolerance:
                return i
        return None

    def _on_click(self, event):
        idx = self._hit_test_boundary(event.x)
        if idx is not None:
            self._dragging_index = idx
            self._drag_start_x = event.x
        else:
            self._dragging_index = None

    def _on_drag(self, event):
        if self._dragging_index is None:
            return
        new_t = self._x_to_time(event.x)
        # Không cho kéo vượt qua boundary liền kề (giữ thứ tự tăng dần)
        i = self._dragging_index
        lower = self.boundaries[i - 1] + 0.05 if i > 0 else 0.05
        upper = self.boundaries[i + 1] - 0.05 if i < len(self.boundaries) - 1 else self.total_duration - 0.05
        new_t = max(lower, min(upper, new_t))
        self.boundaries[i] = new_t
        self.redraw()

    def _on_release(self, event):
        if self._dragging_index is not None:
            self._dragging_index = None
            if self.on_boundaries_changed:
                self.on_boundaries_changed(list(self.boundaries))
            return

        # Không phải thả sau khi kéo -> coi là click chọn đoạn để nghe thử
        idx = self._hit_test_boundary(event.x)
        if idx is None and self.on_segment_click:
            t = self._x_to_time(event.x)
            all_points = [0.0] + self.boundaries + [self.total_duration]
            for seg_i in range(len(all_points) - 1):
                if all_points[seg_i] <= t <= all_points[seg_i + 1]:
                    self.on_segment_click(seg_i)
                    break

    def _on_double_click(self, event):
        idx = self._hit_test_boundary(event.x)
        if idx is not None:
            del self.boundaries[idx]
            self.redraw()
            if self.on_boundaries_changed:
                self.on_boundaries_changed(list(self.boundaries))

    def _on_right_click(self, event):
        t = self._x_to_time(event.x)
        # tránh thêm điểm cắt quá sát điểm đã có
        if all(abs(t - b) > 0.1 for b in self.boundaries):
            self.boundaries.append(t)
            self.boundaries.sort()
            self.redraw()
            if self.on_boundaries_changed:
                self.on_boundaries_changed(list(self.boundaries))

    # ---------------------------------------------------------------- API cho bên ngoài
    def get_segments_as_ranges(self):
        """Trả về list (start_s, end_s) theo boundary HIỆN TẠI (đã qua chỉnh tay nếu có)."""
        all_points = [0.0] + list(self.boundaries) + [self.total_duration]
        return [(all_points[i], all_points[i + 1]) for i in range(len(all_points) - 1)]

    def set_peaks(self, peaks: List[float], total_duration: float, boundaries: List[float]):
        """Nạp lại dữ liệu mới (khi đổi file audio khác)."""
        self.peaks = peaks
        self.total_duration = total_duration
        self.boundaries = sorted(boundaries)
        self.redraw()
