# -*- coding: utf-8 -*-
"""
ZOLO Auto CapCut - GUI chính
Module đã hoàn thiện: Đồng bộ âm thanh (JSON, an toàn, chạy được ngay).
Module cần calibrate thêm trên máy Windows thật: Auto Render (UI automation).

Chạy: python zolo_autocapcut_gui.py
"""

import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox, filedialog

from draft_utils import default_projects_root, list_drafts
from audio_sync import sync_draft
from audio_splitter import (
    split_by_silence, get_audio_duration, analyze_silence, segments_from_silence,
    split_audio, get_waveform_peaks, Segment,
)
from waveform_widget import WaveformEditor
import audio_preview

try:
    import draft_builder
except Exception:
    draft_builder = None

try:
    import captions_module
except Exception:
    captions_module = None

try:
    import auto_render
except Exception:
    auto_render = None


class ZoloAutoCapCutApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ZOLO Auto CapCut v1.0")
        self.geometry("900x560")
        self.configure(bg="white")

        self.projects_root = default_projects_root()
        self.drafts = []          # list dict từ list_drafts()
        self.draft_vars = {}      # draft_name -> tk.BooleanVar (checkbox)
        self.stop_flag = threading.Event()

        self._build_ui()
        self.refresh_drafts()

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Treeview", background="white", fieldbackground="white",
                         foreground="black", rowheight=24)
        style.configure("TButton", padding=4)

        # ---- Thanh đường dẫn ----
        top = tk.Frame(self, bg="white", highlightbackground="black", highlightthickness=1)
        top.pack(fill="x", padx=8, pady=(8, 4))

        tk.Label(top, text="Thư mục Projects CapCut:", bg="white").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        self.path_var = tk.StringVar(value=str(self.projects_root))
        tk.Entry(top, textvariable=self.path_var, width=70).grid(row=0, column=1, padx=4, pady=4, sticky="we")
        tk.Button(top, text="Chọn...", command=self._choose_root).grid(row=0, column=2, padx=4)
        top.columnconfigure(1, weight=1)

        # ---- Khung chính: trái = danh sách draft, phải = điều khiển ----
        main = tk.Frame(self, bg="white")
        main.pack(fill="both", expand=True, padx=8, pady=4)

        left = tk.Frame(main, bg="white", highlightbackground="black", highlightthickness=1)
        left.pack(side="left", fill="both", expand=True, padx=(0, 4))

        columns = ("status",)
        self.tree = ttk.Treeview(left, columns=columns, show="tree headings", selectmode="none")
        self.tree.heading("#0", text="Draft")
        self.tree.heading("status", text="Trạng thái")
        self.tree.column("#0", width=380)
        self.tree.column("status", width=200)
        self.tree.pack(fill="both", expand=True, side="left")
        self.tree.bind("<Button-1>", self._on_tree_click)

        scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scroll.set)

        right = tk.Frame(main, bg="white", width=280, highlightbackground="black", highlightthickness=1)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)

        # Khung nút dùng chung (Refresh/Output) - pack side="bottom" TRƯỚC để giữ chỗ,
        # nếu không notebook (fill=both, expand=True) sẽ chiếm hết diện tích.
        common_frame = tk.Frame(right, bg="white")
        common_frame.pack(side="bottom", fill="x")
        tk.Button(common_frame, text="Refresh danh sách", command=self.refresh_drafts).pack(fill="x", padx=10, pady=(10, 2))
        tk.Button(common_frame, text="Mở thư mục Output", command=self._open_output).pack(fill="x", padx=10, pady=2)

        notebook = ttk.Notebook(right)
        notebook.pack(side="top", fill="both", expand=True)

        tab_sync = tk.Frame(notebook, bg="white")
        tab_split = tk.Frame(notebook, bg="white")
        tab_build = tk.Frame(notebook, bg="white")
        tab_caption = tk.Frame(notebook, bg="white")
        notebook.add(tab_sync, text="Sync && Render")
        notebook.add(tab_split, text="Audio Splitter")
        notebook.add(tab_build, text="Draft Builder")
        notebook.add(tab_caption, text="Sub/Caption")

        self._build_sync_tab(tab_sync)
        self._build_split_tab(tab_split)
        self._build_builder_tab(tab_build)
        self._build_caption_tab(tab_caption)

        # ---- Log phía dưới cùng cửa sổ ----
        bottom = tk.Frame(self, bg="white", highlightbackground="black", highlightthickness=1)
        bottom.pack(fill="both", padx=8, pady=(4, 8))
        tk.Label(bottom, text="LOG", bg="white", anchor="w").pack(fill="x")
        self.log_box = tk.Text(bottom, height=8, bg="white", fg="black", state="disabled")
        self.log_box.pack(fill="both", expand=True)

    def _build_sync_tab(self, right):
        tk.Label(right, text="ĐỒNG BỘ ÂM THANH", bg="white", font=("Segoe UI", 9, "bold")).pack(pady=(10, 2))

        self.sync_mode = tk.StringVar(value="pair")
        tk.Radiobutton(right, text="Ghép theo cặp (Story/TikTok)", variable=self.sync_mode,
                        value="pair", bg="white", anchor="w").pack(fill="x", padx=10)
        tk.Radiobutton(right, text="Tổng thời lượng (Classic/Mixed)", variable=self.sync_mode,
                        value="total", bg="white", anchor="w").pack(fill="x", padx=10)

        tk.Button(right, text="Xem trước (Preview)", command=self._preview_sync).pack(fill="x", padx=10, pady=(8, 2))
        tk.Button(right, text="Đồng bộ âm thanh (Apply)", command=self._apply_sync).pack(fill="x", padx=10, pady=2)

        ttk.Separator(right, orient="horizontal").pack(fill="x", pady=10, padx=6)

        tk.Label(right, text="AUTO RENDER", bg="white", font=("Segoe UI", 9, "bold")).pack(pady=2)
        tk.Label(right, text="(cần calibrate trên máy Windows\ntrước khi dùng - xem auto_render.py)",
                 bg="white", fg="#a33", justify="left", font=("Segoe UI", 8)).pack(padx=10)

        self.output_dir_var = tk.StringVar(value=str(Path.home() / "Desktop" / "ZOLO_Output"))
        tk.Entry(right, textvariable=self.output_dir_var).pack(fill="x", padx=10, pady=(6, 2))
        tk.Button(right, text="Chọn thư mục Output...", command=self._choose_output).pack(fill="x", padx=10)

        btn_frame = tk.Frame(right, bg="white")
        btn_frame.pack(fill="x", padx=10, pady=8)
        tk.Button(btn_frame, text="🚀 Auto Render", command=self._start_render).pack(side="left", expand=True, fill="x")
        tk.Button(btn_frame, text="Stop", fg="red", command=self._stop_render).pack(side="left", expand=True, fill="x")

    def _build_split_tab(self, right):
        tk.Label(right, text="TÁCH AUDIO DÀI THÀNH ĐOẠN", bg="white",
                 font=("Segoe UI", 9, "bold"), wraplength=250, justify="left").pack(pady=(10, 2))

        self.split_file_var = tk.StringVar(value="(chưa chọn file)")
        tk.Button(right, text="Chọn file audio...", command=self._choose_split_file).pack(fill="x", padx=10, pady=(8, 2))
        tk.Label(right, textvariable=self.split_file_var, bg="white", fg="#555",
                 wraplength=250, justify="left", font=("Segoe UI", 8)).pack(fill="x", padx=10)

        ttk.Separator(right, orient="horizontal").pack(fill="x", pady=8, padx=6)

        self.split_mode = tk.StringVar(value="sentence")
        tk.Radiobutton(right, text="Theo câu (khoảng lặng)", variable=self.split_mode,
                        value="sentence", bg="white", anchor="w").pack(fill="x", padx=10)
        tk.Radiobutton(right, text="Chia đều số lượng", variable=self.split_mode,
                        value="count", bg="white", anchor="w").pack(fill="x", padx=10)

        row1 = tk.Frame(right, bg="white")
        row1.pack(fill="x", padx=10, pady=(6, 2))
        tk.Label(row1, text="Câu/đoạn:", bg="white").pack(side="left")
        self.sentences_per_seg_var = tk.IntVar(value=1)
        tk.Spinbox(row1, from_=1, to=20, textvariable=self.sentences_per_seg_var, width=5).pack(side="left", padx=4)

        row2 = tk.Frame(right, bg="white")
        row2.pack(fill="x", padx=10, pady=2)
        tk.Label(row2, text="Số đoạn (mode chia đều):", bg="white").pack(side="left")
        self.target_count_var = tk.IntVar(value=5)
        tk.Spinbox(row2, from_=2, to=100, textvariable=self.target_count_var, width=5).pack(side="left", padx=4)

        row3 = tk.Frame(right, bg="white")
        row3.pack(fill="x", padx=10, pady=2)
        tk.Label(row3, text="Ngưỡng lặng (dB):", bg="white").pack(side="left")
        self.silence_db_var = tk.IntVar(value=-35)
        tk.Spinbox(row3, from_=-60, to=-10, textvariable=self.silence_db_var, width=5).pack(side="left", padx=4)

        tk.Button(right, text="👁️ Xem trước & Tách Audio", command=self._start_split).pack(fill="x", padx=10, pady=(12, 2))

        self.split_result_var = tk.StringVar(value="")
        tk.Label(right, textvariable=self.split_result_var, bg="white", fg="#070",
                 wraplength=250, justify="left", font=("Segoe UI", 8)).pack(fill="x", padx=10, pady=4)

    def _build_builder_tab(self, right):
        tk.Label(right, text="DỰNG DRAFT TỪ ẢNH/VIDEO + AUDIO", bg="white",
                 font=("Segoe UI", 9, "bold"), wraplength=250, justify="left").pack(pady=(10, 2))

        self.build_name_var = tk.StringVar(value="ZOLO_Draft_01")
        tk.Label(right, text="Tên draft:", bg="white", anchor="w").pack(fill="x", padx=10, pady=(8, 0))
        tk.Entry(right, textvariable=self.build_name_var).pack(fill="x", padx=10)

        self.build_media_var = tk.StringVar(value="(chưa chọn thư mục ảnh/video)")
        tk.Button(right, text="Chọn thư mục ảnh/video...", command=self._choose_build_media).pack(
            fill="x", padx=10, pady=(10, 2))
        tk.Label(right, textvariable=self.build_media_var, bg="white", fg="#555",
                 wraplength=250, justify="left", font=("Segoe UI", 8)).pack(fill="x", padx=10)

        self.build_audio_var = tk.StringVar(value="(chưa chọn thư mục audio đã tách)")
        tk.Button(right, text="Chọn thư mục audio đã tách...", command=self._choose_build_audio).pack(
            fill="x", padx=10, pady=(10, 2))
        tk.Label(right, textvariable=self.build_audio_var, bg="white", fg="#555",
                 wraplength=250, justify="left", font=("Segoe UI", 8)).pack(fill="x", padx=10)

        ttk.Separator(right, orient="horizontal").pack(fill="x", pady=8, padx=6)

        size_row = tk.Frame(right, bg="white")
        size_row.pack(fill="x", padx=10, pady=2)
        tk.Label(size_row, text="Khung hình:", bg="white").pack(side="left")
        self.build_ratio_var = tk.StringVar(value="9:16 (1080x1920)")
        ttk.Combobox(size_row, textvariable=self.build_ratio_var, state="readonly", width=16,
                     values=["9:16 (1080x1920)", "16:9 (1920x1080)", "1:1 (1080x1080)"]).pack(side="left", padx=4)

        ttk.Separator(right, orient="horizontal").pack(fill="x", pady=8, padx=6)

        tk.Label(right, text="Hiệu ứng tự động gắn:", bg="white", anchor="w").pack(fill="x", padx=10)
        self.fx_intro_var = tk.BooleanVar(value=True)
        self.fx_transition_var = tk.BooleanVar(value=True)
        self.fx_filter_var = tk.BooleanVar(value=False)
        self.fx_kenburns_var = tk.BooleanVar(value=True)
        self.fx_mask_var = tk.BooleanVar(value=False)
        tk.Checkbutton(right, text="Animation vào (intro)", variable=self.fx_intro_var,
                        bg="white", anchor="w").pack(fill="x", padx=14)
        tk.Checkbutton(right, text="Transition giữa các đoạn", variable=self.fx_transition_var,
                        bg="white", anchor="w").pack(fill="x", padx=14)
        tk.Checkbutton(right, text="Filter màu", variable=self.fx_filter_var,
                        bg="white", anchor="w").pack(fill="x", padx=14)
        tk.Checkbutton(right, text="Ken Burns (zoom nhẹ dần)", variable=self.fx_kenburns_var,
                        bg="white", anchor="w").pack(fill="x", padx=14)
        tk.Checkbutton(right, text="Mask (khung tròn/tim/sao...)", variable=self.fx_mask_var,
                        bg="white", anchor="w").pack(fill="x", padx=14)

        tk.Button(right, text="🎬 Dựng Draft", command=self._start_build).pack(fill="x", padx=10, pady=(14, 2))

        self.build_result_var = tk.StringVar(value="")
        tk.Label(right, textvariable=self.build_result_var, bg="white", fg="#070",
                 wraplength=250, justify="left", font=("Segoe UI", 8)).pack(fill="x", padx=10, pady=4)

    def _build_caption_tab(self, right):
        tk.Label(right, text="IMPORT / EXPORT SUB (SRT) HÀNG LOẠT", bg="white",
                 font=("Segoe UI", 9, "bold"), wraplength=250, justify="left").pack(pady=(10, 2))
        tk.Label(right, text="Dùng danh sách draft đã tick ☑ bên trái.\n"
                              "Ghép theo tên: <thư_mục_srt>/<tên_draft>.srt",
                 bg="white", fg="#555", wraplength=250, justify="left", font=("Segoe UI", 8)).pack(
            fill="x", padx=10, pady=(0, 6))

        self.srt_folder_var = tk.StringVar(value="(chưa chọn thư mục SRT)")
        tk.Button(right, text="Chọn thư mục SRT...", command=self._choose_srt_folder).pack(
            fill="x", padx=10, pady=(4, 2))
        tk.Label(right, textvariable=self.srt_folder_var, bg="white", fg="#555",
                 wraplength=250, justify="left", font=("Segoe UI", 8)).pack(fill="x", padx=10)

        row = tk.Frame(right, bg="white")
        row.pack(fill="x", padx=10, pady=(8, 2))
        tk.Label(row, text="Track name:", bg="white").pack(side="left")
        self.sub_track_name_var = tk.StringVar(value="ZOLO_sub")
        tk.Entry(row, textvariable=self.sub_track_name_var, width=14).pack(side="left", padx=4)

        row2 = tk.Frame(right, bg="white")
        row2.pack(fill="x", padx=10, pady=2)
        tk.Label(row2, text="Cỡ chữ:", bg="white").pack(side="left")
        self.sub_font_size_var = tk.IntVar(value=8)
        tk.Spinbox(row2, from_=4, to=30, textvariable=self.sub_font_size_var, width=5).pack(side="left", padx=4)

        tk.Button(right, text="⬇️ Import SRT vào draft đã tick", command=self._start_import_srt).pack(
            fill="x", padx=10, pady=(12, 2))

        ttk.Separator(right, orient="horizontal").pack(fill="x", pady=8, padx=6)

        tk.Button(right, text="⬆️ Export SRT từ draft đã tick", command=self._start_export_srt).pack(
            fill="x", padx=10, pady=2)

        self.caption_result_var = tk.StringVar(value="")
        tk.Label(right, textvariable=self.caption_result_var, bg="white", fg="#070",
                 wraplength=250, justify="left", font=("Segoe UI", 8)).pack(fill="x", padx=10, pady=4)

    # ---------------------------------------------------------------- helpers
    def log(self, msg: str):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _choose_root(self):
        d = filedialog.askdirectory(initialdir=self.path_var.get())
        if d:
            self.path_var.set(d)
            self.refresh_drafts()

    def _choose_output(self):
        d = filedialog.askdirectory(initialdir=self.output_dir_var.get())
        if d:
            self.output_dir_var.set(d)

    def _open_output(self):
        import os
        out = Path(self.output_dir_var.get())
        out.mkdir(parents=True, exist_ok=True)
        os.startfile(out)  # chỉ chạy trên Windows

    # ---------------------------------------------------------------- draft list
    def refresh_drafts(self):
        self.tree.delete(*self.tree.get_children())
        self.draft_vars.clear()
        root = Path(self.path_var.get())
        self.drafts = list_drafts(root)

        if not self.drafts:
            self.log(f"Không tìm thấy draft nào trong: {root}")
            return

        for d in self.drafts:
            var = tk.BooleanVar(value=True)
            self.draft_vars[d["name"]] = var
            self.tree.insert("", "end", iid=d["name"], text=f"☑ {d['name']}", values=("Sẵn sàng",))

        self.log(f"Đã tải {len(self.drafts)} draft.")

    def _on_tree_click(self, event):
        # click vào cột #0 (tên) để toggle checkbox
        region = self.tree.identify_region(event.x, event.y)
        if region != "tree":
            return
        item = self.tree.identify_row(event.y)
        if not item:
            return
        var = self.draft_vars.get(item)
        if var is None:
            return
        var.set(not var.get())
        prefix = "☑" if var.get() else "☐"
        self.tree.item(item, text=f"{prefix} {item}")

    def _selected_drafts(self):
        return [d for d in self.drafts if self.draft_vars.get(d["name"], tk.BooleanVar(value=False)).get()]

    def _set_status(self, draft_name, status):
        if self.tree.exists(draft_name):
            self.tree.set(draft_name, "status", status)

    # ---------------------------------------------------------------- sync âm thanh
    def _preview_sync(self):
        self._run_sync(apply=False)

    def _apply_sync(self):
        if not messagebox.askyesno("Xác nhận",
                                    "Sẽ ghi đè draft_content.json của các project đã chọn "
                                    "(có backup tự động .bak). Tiếp tục?"):
            return
        self._run_sync(apply=True)

    def _run_sync(self, apply: bool):
        selected = self._selected_drafts()
        if not selected:
            messagebox.showwarning("Chưa chọn", "Chưa chọn draft nào.")
            return

        mode = self.sync_mode.get()
        for d in selected:
            try:
                changes, _ = sync_draft(d["json_path"], mode=mode, apply=apply)
            except Exception as e:
                self.log(f"[{d['name']}] Lỗi: {e}")
                self._set_status(d["name"], "Lỗi - xem log")
                continue

            if not changes:
                self._set_status(d["name"], "Đã khớp / không cần cắt")
                self.log(f"[{d['name']}] Không có gì cần đồng bộ.")
                continue

            for c in changes:
                self.log(f"[{d['name']}] {c.reason}")

            status = "Đã đồng bộ" if apply else f"Preview: {len(changes)} thay đổi"
            self._set_status(d["name"], status)

    # ---------------------------------------------------------------- audio splitter
    def _choose_split_file(self):
        f = filedialog.askopenfilename(
            title="Chọn file audio",
            filetypes=[("Audio files", "*.mp3 *.wav *.m4a *.aac *.flac"), ("Tất cả", "*.*")],
        )
        if f:
            self.split_file_var.set(f)

    def _start_split(self):
        """Bấm 'Tách Audio' giờ KHÔNG tách ngay, mà mở cửa sổ waveform để xem trước
        + chỉnh tay điểm cắt + nghe thử, giống trải nghiệm VibeCut. Tách thật chỉ
        xảy ra khi bấm 'Xác nhận' trong cửa sổ đó."""
        file_path = self.split_file_var.get()
        if not file_path or file_path == "(chưa chọn file)":
            messagebox.showwarning("Chưa chọn file", "Chưa chọn file audio để tách.")
            return

        self.log(f"Đang phân tích waveform: {Path(file_path).name}...")
        thread = threading.Thread(target=self._analyze_and_open_editor, args=(Path(file_path),), daemon=True)
        thread.start()

    def _analyze_and_open_editor(self, file_path: Path):
        try:
            duration = get_audio_duration(file_path)
            silences = analyze_silence(file_path, self.silence_db_var.get(), 0.15)
            initial_segments = segments_from_silence(
                duration, silences, mode=self.split_mode.get(),
                sentences_per_segment=self.sentences_per_seg_var.get(),
                target_count=self.target_count_var.get(),
            )
            peaks = get_waveform_peaks(file_path, num_peaks=1000)
        except Exception as e:
            self.log(f"Lỗi phân tích waveform: {e}")
            return

        # boundary = điểm start của mọi segment TRỪ đoạn đầu tiên (đoạn đầu luôn bắt đầu từ 0)
        boundaries = [s.start for s in initial_segments[1:]]

        self.after(0, lambda: self._open_waveform_window(file_path, peaks, duration, boundaries))

    def _open_waveform_window(self, file_path: Path, peaks, duration: float, boundaries: list):
        win = tk.Toplevel(self)
        win.title(f"Xem trước Waveform - {file_path.name}")
        win.geometry("960x320")
        win.configure(bg="white")

        tk.Label(win, text="Kéo vạch đỏ = chỉnh điểm cắt | Click vào đoạn = nghe thử | "
                            "Click PHẢI = thêm điểm cắt | Double-click vạch đỏ = xoá điểm cắt",
                 bg="white", fg="#555", font=("Segoe UI", 8)).pack(fill="x", padx=8, pady=(6, 2))

        info_var = tk.StringVar(value="")

        def on_segment_click(idx):
            ranges = editor.get_segments_as_ranges()
            if idx >= len(ranges):
                return
            start_s, end_s = ranges[idx]
            info_var.set(f"Đang nghe đoạn #{idx+1}: {start_s:.2f}s -> {end_s:.2f}s ({end_s-start_s:.2f}s)")
            threading.Thread(target=self._play_preview, args=(file_path, start_s, end_s), daemon=True).start()

        def on_boundaries_changed(new_boundaries):
            ranges = editor.get_segments_as_ranges()
            info_var.set(f"{len(ranges)} đoạn - đã chỉnh tay điểm cắt")

        editor = WaveformEditor(win, peaks, duration, boundaries,
                                 on_segment_click=on_segment_click,
                                 on_boundaries_changed=on_boundaries_changed,
                                 height=160)
        editor.pack(fill="x", padx=8, pady=4)

        tk.Label(win, textvariable=info_var, bg="white", fg="#070", font=("Segoe UI", 8)).pack(
            fill="x", padx=8, pady=2)

        btn_row = tk.Frame(win, bg="white")
        btn_row.pack(fill="x", padx=8, pady=10)
        tk.Button(btn_row, text="⏹ Dừng phát", command=audio_preview.stop).pack(side="left", padx=4)
        tk.Button(btn_row, text="Huỷ", command=win.destroy).pack(side="right", padx=4)
        tk.Button(btn_row, text="✅ Xác nhận & Tách Audio", bg="#dff0d8",
                  command=lambda: self._confirm_split(file_path, editor, win)).pack(side="right", padx=4)

        info_var.set(f"{len(editor.get_segments_as_ranges())} đoạn (tự động phát hiện từ khoảng lặng)")

    def _play_preview(self, file_path: Path, start_s: float, end_s: float):
        try:
            audio_preview.play_segment(file_path, start_s, end_s)
        except Exception as e:
            self.log(f"Không phát được preview: {e}")

    def _confirm_split(self, file_path: Path, editor: WaveformEditor, win: tk.Toplevel):
        ranges = editor.get_segments_as_ranges()
        segments = [Segment(index=i + 1, start=s, end=e) for i, (s, e) in enumerate(ranges)]
        out_dir = Path(self.output_dir_var.get()) / f"split_{file_path.stem}"

        win.destroy()
        thread = threading.Thread(target=self._split_worker, args=(file_path, out_dir, segments), daemon=True)
        thread.start()

    def _split_worker(self, file_path: Path, out_dir: Path, segments=None):
        self.log(f"Bắt đầu tách: {file_path.name}")
        try:
            if segments is not None:
                # Dùng đúng điểm cắt người dùng đã xem/chỉnh trong waveform editor
                split_audio(file_path, segments, out_dir)
            else:
                segments = split_by_silence(
                    file_path, out_dir,
                    silence_threshold_db=self.silence_db_var.get(),
                    min_silence_duration=0.15,
                    mode=self.split_mode.get(),
                    sentences_per_segment=self.sentences_per_seg_var.get(),
                    target_count=self.target_count_var.get(),
                )
        except Exception as e:
            self.log(f"Lỗi tách audio: {e}")
            self.split_result_var.set("Lỗi - xem log")
            return

        for s in segments:
            self.log(f"  #{s.index}: {s.start:.2f}s -> {s.end:.2f}s (dur={s.duration:.2f}s)")

        self.split_result_var.set(f"Đã tách {len(segments)} đoạn vào:\n{out_dir}")
        self.log(f"Xong. Xuất {len(segments)} file vào {out_dir}")

    # ---------------------------------------------------------------- draft builder
    def _choose_build_media(self):
        d = filedialog.askdirectory(title="Chọn thư mục chứa ảnh/video")
        if d:
            self.build_media_var.set(d)

    def _choose_build_audio(self):
        d = filedialog.askdirectory(title="Chọn thư mục chứa audio đã tách (1.mp3, 2.mp3...)")
        if d:
            self.build_audio_var.set(d)

    def _start_build(self):
        if draft_builder is None:
            messagebox.showerror("Thiếu thư viện",
                                  "Chưa cài pyJianYingDraft. Chạy setup.bat để cài lại requirements.txt.")
            return

        media_dir = self.build_media_var.get()
        audio_dir = self.build_audio_var.get()
        if "chưa chọn" in media_dir or "chưa chọn" in audio_dir:
            messagebox.showwarning("Chưa chọn thư mục", "Cần chọn cả thư mục ảnh/video và thư mục audio.")
            return

        ratio_map = {
            "9:16 (1080x1920)": (1080, 1920),
            "16:9 (1920x1080)": (1920, 1080),
            "1:1 (1080x1080)": (1080, 1080),
        }
        width, height = ratio_map[self.build_ratio_var.get()]
        draft_name = self.build_name_var.get().strip() or "ZOLO_Draft"

        thread = threading.Thread(
            target=self._build_worker,
            args=(draft_name, Path(media_dir), Path(audio_dir), width, height),
            daemon=True,
        )
        thread.start()

    def _build_worker(self, draft_name, media_dir: Path, audio_dir: Path, width: int, height: int):
        self.log(f"Bắt đầu dựng draft '{draft_name}'...")
        try:
            result = draft_builder.build_draft_from_folders(
                projects_root=Path(self.path_var.get()),
                draft_name=draft_name,
                media_folder=media_dir,
                audio_folder=audio_dir,
                width=width, height=height, fps=30,
                apply_intro=self.fx_intro_var.get(),
                apply_transition=self.fx_transition_var.get(),
                apply_filter=self.fx_filter_var.get(),
                apply_ken_burns=self.fx_kenburns_var.get(),
                apply_mask=self.fx_mask_var.get(),
            )
        except FileExistsError:
            self.log(f"Lỗi: draft '{draft_name}' đã tồn tại. Đổi tên khác.")
            self.build_result_var.set("Lỗi - draft đã tồn tại, đổi tên khác")
            return
        except Exception as e:
            self.log(f"Lỗi dựng draft: {e}")
            self.build_result_var.set("Lỗi - xem log")
            return

        for w in result["warnings"]:
            self.log(f"[CẢNH BÁO] {w}")
        for seg in result["segments"]:
            fx_str = ", ".join(seg.get("effects", [])) or "(không có hiệu ứng)"
            self.log(f"  #{seg['index']}: {seg['media']} + {seg['audio']} "
                      f"(start={seg['start_s']:.2f}s, dur={seg['duration_s']:.2f}s) | {fx_str}")

        self.build_result_var.set(
            f"Xong! {len(result['segments'])} đoạn, tổng {result['total_duration_s']:.1f}s.\n"
            f"Mở CapCut để xem draft '{draft_name}'."
        )
        self.log(f"Dựng xong draft '{draft_name}' - tổng {result['total_duration_s']:.1f}s. "
                  f"Mở CapCut để kiểm tra + Export.")
        self.after(0, self.refresh_drafts)

    # ---------------------------------------------------------------- sub/caption
    def _choose_srt_folder(self):
        d = filedialog.askdirectory(title="Chọn thư mục chứa file SRT (tên trùng tên draft)")
        if d:
            self.srt_folder_var.set(d)

    def _start_import_srt(self):
        if captions_module is None:
            messagebox.showerror("Thiếu thư viện", "Chưa cài pyJianYingDraft.")
            return
        selected = self._selected_drafts()
        if not selected:
            messagebox.showwarning("Chưa chọn", "Chưa tick draft nào ở danh sách bên trái.")
            return
        srt_folder = self.srt_folder_var.get()
        if "chưa chọn" in srt_folder:
            messagebox.showwarning("Chưa chọn thư mục", "Chưa chọn thư mục chứa file SRT.")
            return

        thread = threading.Thread(target=self._import_srt_worker, args=(selected, Path(srt_folder)), daemon=True)
        thread.start()

    def _import_srt_worker(self, drafts, srt_folder: Path):
        track_name = self.sub_track_name_var.get().strip() or "ZOLO_sub"
        font_size = self.sub_font_size_var.get()
        ok_count, skip_count, fail_count = 0, 0, 0

        for d in drafts:
            srt_path = srt_folder / f"{d['name']}.srt"
            if not srt_path.exists():
                self.log(f"[{d['name']}] Bỏ qua - không tìm thấy {srt_path.name} trong thư mục SRT.")
                self._set_status(d["name"], "Không có SRT khớp tên")
                skip_count += 1
                continue
            try:
                captions_module.import_srt_into_draft(
                    Path(self.path_var.get()), d["name"], srt_path,
                    track_name=track_name, font_size=font_size,
                )
                self.log(f"[{d['name']}] Đã import {srt_path.name} vào track '{track_name}'.")
                self._set_status(d["name"], "Đã import sub")
                ok_count += 1
            except NameError as e:
                self.log(f"[{d['name']}] Bỏ qua - {e}")
                self._set_status(d["name"], "Track sub đã tồn tại")
                skip_count += 1
            except Exception as e:
                self.log(f"[{d['name']}] Lỗi: {e}")
                self._set_status(d["name"], "Lỗi - xem log")
                fail_count += 1

        self.caption_result_var.set(f"Import xong: {ok_count} OK, {skip_count} bỏ qua, {fail_count} lỗi.")
        self.log(f"Hoàn tất import SRT hàng loạt: {ok_count} OK, {skip_count} bỏ qua, {fail_count} lỗi.")

    def _start_export_srt(self):
        if captions_module is None:
            messagebox.showerror("Thiếu thư viện", "Chưa cài pyJianYingDraft.")
            return
        selected = self._selected_drafts()
        if not selected:
            messagebox.showwarning("Chưa chọn", "Chưa tick draft nào ở danh sách bên trái.")
            return

        out_dir = Path(self.output_dir_var.get()) / "exported_subs"
        thread = threading.Thread(target=self._export_srt_worker, args=(selected, out_dir), daemon=True)
        thread.start()

    def _export_srt_worker(self, drafts, out_dir: Path):
        track_name = self.sub_track_name_var.get().strip() or None
        ok_count, fail_count = 0, 0

        for d in drafts:
            out_path = out_dir / f"{d['name']}.srt"
            try:
                result = captions_module.export_srt_from_draft(
                    Path(self.path_var.get()), d["name"], out_path, track_name=track_name,
                )
                self.log(f"[{d['name']}] Đã xuất {result['count']} dòng sub -> {out_path.name}")
                ok_count += 1
            except Exception as e:
                self.log(f"[{d['name']}] Lỗi export: {e}")
                fail_count += 1

        self.caption_result_var.set(f"Export xong: {ok_count} OK, {fail_count} lỗi.\nVào: {out_dir}")
        self.log(f"Hoàn tất export SRT hàng loạt vào {out_dir}: {ok_count} OK, {fail_count} lỗi.")

    # ---------------------------------------------------------------- auto render
    def _start_render(self):
        if auto_render is None or auto_render.Application is None:
            messagebox.showerror("Chưa sẵn sàng",
                                  "auto_render.py cần chạy trên Windows với pywinauto đã cài, "
                                  "và cần calibrate CONTROL_NAMES trước (xem hướng dẫn trong file).")
            return

        selected = self._selected_drafts()
        if not selected:
            messagebox.showwarning("Chưa chọn", "Chưa chọn draft nào.")
            return

        self.stop_flag.clear()
        out_dir = Path(self.output_dir_var.get())
        out_dir.mkdir(parents=True, exist_ok=True)

        thread = threading.Thread(target=self._render_worker, args=(selected, out_dir), daemon=True)
        thread.start()

    def _render_worker(self, drafts, out_dir):
        for d in drafts:
            if self.stop_flag.is_set():
                self.log("Đã dừng theo yêu cầu.")
                break
            self._set_status(d["name"], "Đang render...")
            self.log(f"[{d['name']}] Bắt đầu render...")
            try:
                ok = auto_render.render_one_project(
                    capcut_exe_path=auto_render.CAPCUT_EXE_PATH,
                    project_name=d["name"],
                    output_dir=out_dir,
                )
            except Exception as e:
                self.log(f"[{d['name']}] Lỗi render: {e}")
                self._set_status(d["name"], "Lỗi - xem log")
                continue

            self._set_status(d["name"], "Xong" if ok else "Timeout/Thất bại")
            self.log(f"[{d['name']}] {'Render xong.' if ok else 'Timeout hoặc thất bại.'}")

    def _stop_render(self):
        self.stop_flag.set()
        self.log("Đã gửi tín hiệu dừng - chờ project hiện tại xử lý xong.")


if __name__ == "__main__":
    app = ZoloAutoCapCutApp()
    app.mainloop()
