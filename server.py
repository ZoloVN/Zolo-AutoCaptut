# -*- coding: utf-8 -*-
"""
server.py
Backend Flask cho giao diện web ZOLO Auto CapCut - KHÔNG viết lại logic, chỉ bọc API
lên trên các module đã test (draft_utils, audio_splitter, draft_builder, effects_module,
captions_module, audio_sync). Chạy local-only (127.0.0.1), 1 người dùng, không cần auth.

Chạy: python server.py, rồi mở http://127.0.0.1:5757
"""

import tempfile
import threading
import traceback
from pathlib import Path

from flask import Flask, request, jsonify, send_from_directory, send_file

import draft_utils
import audio_splitter
import audio_sync
import draft_builder
import effects_module
import captions_module
import sticker_module
import voice_srt_align
import batch_module
import video_splitter
import file_rename_module

app = Flask(__name__, static_folder="static", static_url_path="")


def _ok(**kwargs):
    return jsonify({"success": True, **kwargs})


def _err(message, code=400):
    return jsonify({"success": False, "error": str(message)}), code


# ─── Trang chính ───

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


# ─── Draft list ───

@app.route("/api/default_root")
def api_default_root():
    return _ok(root=str(draft_utils.default_projects_root()))


@app.route("/api/drafts")
def api_drafts():
    root = request.args.get("root", "")
    if not root:
        return _err("Thiếu tham số root")
    try:
        drafts = draft_utils.list_drafts(Path(root))
        return _ok(drafts=[{"name": d["name"], "modified": d["modified"]} for d in drafts])
    except Exception as e:
        return _err(e)


# ─── Native folder/file picker (dùng tkinter filedialog ẩn - vẫn native dù UI là web) ───

_dialog_lock = threading.Lock()


def _native_dialog(kind: str, **kwargs):
    """Mở dialog native của hệ điều hành qua tkinter (ẩn cửa sổ chính) - chạy tuần tự
    (lock) vì tkinter không an toàn khi gọi đa luồng đồng thời."""
    import tkinter as tk
    from tkinter import filedialog

    with _dialog_lock:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            if kind == "folder":
                path = filedialog.askdirectory(title=kwargs.get("title", "Chọn thư mục"))
            elif kind == "open_file":
                path = filedialog.askopenfilename(
                    title=kwargs.get("title", "Chọn file"),
                    filetypes=kwargs.get("filetypes", [("Tất cả", "*.*")]),
                )
            elif kind == "open_files":
                paths = filedialog.askopenfilenames(
                    title=kwargs.get("title", "Chọn nhiều file"),
                    filetypes=kwargs.get("filetypes", [("Tất cả", "*.*")]),
                )
                return list(paths)
            else:
                path = ""
        finally:
            root.destroy()
        return path


@app.route("/api/browse/folder", methods=["POST"])
def api_browse_folder():
    data = request.get_json(force=True) or {}
    path = _native_dialog("folder", title=data.get("title", "Chọn thư mục"))
    return _ok(path=path)


@app.route("/api/browse/audio_file", methods=["POST"])
def api_browse_audio_file():
    path = _native_dialog("open_file", title="Chọn file audio",
                           filetypes=[("Audio", "*.mp3 *.wav *.m4a *.aac *.flac"), ("Tất cả", "*.*")])
    return _ok(path=path)


@app.route("/api/browse/srt_file", methods=["POST"])
def api_browse_srt_file():
    path = _native_dialog("open_file", title="Chọn file SRT",
                           filetypes=[("SRT", "*.srt"), ("Tất cả", "*.*")])
    return _ok(path=path)


@app.route("/api/browse/video_file", methods=["POST"])
def api_browse_video_file():
    path = _native_dialog("open_file", title="Chọn file video",
                           filetypes=[("Video", "*.mp4 *.mov *.mkv *.avi *.webm"), ("Tất cả", "*.*")])
    return _ok(path=path)


@app.route("/api/browse/multi_files", methods=["POST"])
def api_browse_multi_files():
    paths = _native_dialog("open_files", title="Chọn nhiều file (giữ Ctrl/Shift để chọn nhiều)")
    return _ok(paths=paths)


@app.route("/api/filerename/execute", methods=["POST"])
def api_filerename_execute():
    data = request.get_json(force=True)
    try:
        result = file_rename_module.rename_and_arrange(
            file_paths=data["file_paths"],
            output_dir=Path(data["output_dir"]),
            start_index=data.get("start_index", 1),
        )
        return _ok(result=result)
    except Exception as e:
        traceback.print_exc()
        return _err(e)


# ─── Audio Splitter + Waveform ───

@app.route("/api/audio/waveform", methods=["POST"])
def api_audio_waveform():
    data = request.get_json(force=True)
    file_path = Path(data["file_path"])
    if not file_path.exists():
        return _err("Không tìm thấy file audio")

    try:
        duration = audio_splitter.get_audio_duration(file_path)
        silences = audio_splitter.analyze_silence(
            file_path, data.get("silence_db", -35), data.get("min_silence_duration", 0.15))
        segments = audio_splitter.segments_from_silence(
            duration, silences, mode=data.get("mode", "sentence"),
            sentences_per_segment=data.get("sentences_per_segment", 1),
            target_count=data.get("target_count", 5),
        )
        peaks = audio_splitter.get_waveform_peaks(file_path, num_peaks=data.get("num_peaks", 1000))
        boundaries = [s.start for s in segments[1:]]
        return _ok(duration=duration, peaks=peaks, boundaries=boundaries)
    except Exception as e:
        traceback.print_exc()
        return _err(e)


@app.route("/api/audio/preview", methods=["POST"])
def api_audio_preview():
    """Cắt đoạn tạm và trả về file WAV cho trình duyệt tự phát bằng <audio> - đơn giản
    và ổn định hơn nhiều so với phát âm thanh phía server (không cần pygame/loa server)."""
    data = request.get_json(force=True)
    file_path = Path(data["file_path"])
    start_s = float(data["start"])
    end_s = float(data["end"])

    tmp_dir = Path(tempfile.gettempdir()) / "zolo_web_preview"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    out_path = tmp_dir / f"preview_{int(start_s*1000)}_{int(end_s*1000)}.wav"

    import subprocess
    try:
        subprocess.run([
            "ffmpeg", "-i", str(file_path), "-ss", f"{start_s:.3f}", "-t", f"{end_s-start_s:.3f}",
            "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2", "-y", str(out_path),
        ], capture_output=True, timeout=30, check=True)
    except Exception as e:
        return _err(e)

    return send_file(out_path, mimetype="audio/wav")


@app.route("/api/audio/split", methods=["POST"])
def api_audio_split():
    data = request.get_json(force=True)
    file_path = Path(data["file_path"])
    output_dir = Path(data["output_dir"])
    ranges = data["segments"]  # [[start,end], ...]

    segments = [audio_splitter.Segment(index=i + 1, start=s, end=e) for i, (s, e) in enumerate(ranges)]
    try:
        paths = audio_splitter.split_audio(file_path, segments, output_dir)
        return _ok(output_dir=str(output_dir), files=[p.name for p in paths])
    except Exception as e:
        traceback.print_exc()
        return _err(e)


# ─── Draft Builder ───

@app.route("/api/draft/build", methods=["POST"])
def api_draft_build():
    data = request.get_json(force=True)
    try:
        result = draft_builder.build_draft_from_folders(
            projects_root=Path(data["projects_root"]),
            draft_name=data["draft_name"],
            media_folder=Path(data["media_folder"]),
            audio_folder=Path(data["audio_folder"]),
            width=data.get("width", 1080),
            height=data.get("height", 1920),
            fps=data.get("fps", 30),
            apply_intro=data.get("apply_intro", False),
            intro_pool=data.get("intro_pool"),
            apply_transition=data.get("apply_transition", False),
            transition_pool=data.get("transition_pool"),
            apply_filter=data.get("apply_filter", False),
            filter_pool=data.get("filter_pool"),
            apply_named_motion=data.get("apply_named_motion", False),
            named_motion_pool=data.get("named_motion_pool"),
            apply_mask=data.get("apply_mask", False),
            mask_pool=data.get("mask_pool"),
        )
        return _ok(result=result)
    except FileExistsError:
        return _err(f"Draft '{data.get('draft_name')}' đã tồn tại - đổi tên khác.")
    except Exception as e:
        traceback.print_exc()
        return _err(e)


# ─── Sub/Caption ───

@app.route("/api/captions/import", methods=["POST"])
def api_captions_import():
    data = request.get_json(force=True)
    try:
        result = captions_module.import_srt_into_draft(
            Path(data["projects_root"]), data["draft_name"], Path(data["srt_path"]),
            track_name=data.get("track_name", "ZOLO_sub"),
            font_size=data.get("font_size", 8),
        )
        return _ok(result=result)
    except NameError as e:
        return _err(str(e))
    except Exception as e:
        traceback.print_exc()
        return _err(e)


@app.route("/api/captions/import_animated", methods=["POST"])
def api_captions_import_animated():
    data = request.get_json(force=True)
    try:
        result = captions_module.import_srt_with_animation(
            Path(data["projects_root"]), data["draft_name"], Path(data["srt_path"]),
            track_name=data.get("track_name", "ZOLO_sub"),
            font_size=data.get("font_size", 8),
        )
        return _ok(result=result)
    except NameError as e:
        return _err(str(e))
    except Exception as e:
        traceback.print_exc()
        return _err(e)


@app.route("/api/captions/export", methods=["POST"])
def api_captions_export():
    data = request.get_json(force=True)
    try:
        result = captions_module.export_srt_from_draft(
            Path(data["projects_root"]), data["draft_name"], Path(data["output_path"]),
            track_name=data.get("track_name"),
        )
        return _ok(result=result)
    except Exception as e:
        traceback.print_exc()
        return _err(e)


# ─── Đồng bộ âm thanh ───

@app.route("/api/sync/run", methods=["POST"])
def api_sync_run():
    data = request.get_json(force=True)
    root = Path(data["projects_root"])
    draft_names = data["draft_names"]
    mode = data.get("mode", "pair")
    apply = data.get("apply", False)

    results = []
    for name in draft_names:
        json_path = root / name / "draft_content.json"
        try:
            changes, _ = audio_sync.sync_draft(json_path, mode=mode, apply=apply)
            results.append({
                "draft_name": name,
                "changes": [{"reason": c.reason} for c in changes],
            })
        except Exception as e:
            results.append({"draft_name": name, "error": str(e)})

    return _ok(results=results)


@app.route("/api/sticker/search", methods=["POST"])
def api_sticker_search():
    data = request.get_json(force=True)
    try:
        results = sticker_module.search_sticker(data["keyword"])
        return _ok(results=results)
    except Exception as e:
        traceback.print_exc()
        return _err(e)


@app.route("/api/sticker/add", methods=["POST"])
def api_sticker_add():
    data = request.get_json(force=True)
    try:
        result = sticker_module.add_sticker_to_draft(
            Path(data["projects_root"]), data["draft_name"], data["resource_id"],
            start_s=data["start_s"], end_s=data["end_s"],
            track_name=data.get("track_name", "ZOLO_sticker"),
            scale=data.get("scale", 1.0),
        )
        return _ok(result=result)
    except Exception as e:
        traceback.print_exc()
        return _err(e)


@app.route("/api/voice_align/build", methods=["POST"])
def api_voice_align_build():
    data = request.get_json(force=True)
    try:
        result = voice_srt_align.build_draft_from_srt_voices(
            projects_root=Path(data["projects_root"]),
            draft_name=data["draft_name"],
            srt_path=Path(data["srt_path"]),
            voice_folder=Path(data["voice_folder"]),
            media_folder=Path(data["media_folder"]) if data.get("media_folder") else None,
            mode=data.get("mode", "srt_start"),
            width=data.get("width", 1080),
            height=data.get("height", 1920),
            fps=data.get("fps", 30),
            use_existing_draft=data.get("use_existing_draft", False),
        )
        return _ok(result=result)
    except FileExistsError:
        return _err(f"Draft '{data.get('draft_name')}' đã tồn tại - đổi tên khác.")
    except NameError as e:
        return _err(f"Track đã tồn tại trong draft này (đã chạy tool này trước đó?): {e}")
    except Exception as e:
        traceback.print_exc()
        return _err(e)


@app.route("/api/batch/start", methods=["POST"])
def api_batch_start():
    data = request.get_json(force=True)
    try:
        batch_id = batch_module.start_batch(
            projects_root=data["projects_root"],
            job_configs=data["jobs"],
            parallel_threads=data.get("parallel_threads", 2),
        )
        return _ok(batch_id=batch_id)
    except Exception as e:
        traceback.print_exc()
        return _err(e)


@app.route("/api/batch/status")
def api_batch_status():
    batch_id = request.args.get("batch_id", "")
    status = batch_module.get_batch_status(batch_id)
    if status is None:
        return _err("Không tìm thấy batch (có thể server đã restart)", code=404)
    return _ok(**status)


@app.route("/api/video/split", methods=["POST"])
def api_video_split():
    """Cắt video thật theo segment đã xem/chỉnh trong waveform editor (dùng chung
    endpoint waveform/preview với Audio Splitter vì ffmpeg xử lý audio từ video y hệt)."""
    data = request.get_json(force=True)
    file_path = Path(data["file_path"])
    output_dir = Path(data["output_dir"])
    ranges = data["segments"]  # [[start,end], ...]
    audio_only_indices = data.get("audio_only_indices", [])
    deleted_indices = data.get("deleted_indices", [])

    from audio_splitter import Segment
    segments = [Segment(index=i + 1, start=s, end=e) for i, (s, e) in enumerate(ranges)]
    try:
        results = video_splitter.split_video(
            file_path, segments, output_dir, audio_only_indices, deleted_indices)
        return _ok(output_dir=str(output_dir), outputs=results)
    except Exception as e:
        traceback.print_exc()
        return _err(e)


@app.route("/api/effects/list")
def api_effects_list():
    category = request.args.get("category", "")
    try:
        names = effects_module.list_available(category)
        return _ok(names=names)
    except Exception as e:
        return _err(e)


if __name__ == "__main__":
    print("ZOLO Auto CapCut - server chạy tại http://127.0.0.1:5757")
    app.run(host="127.0.0.1", port=5757, debug=False)
