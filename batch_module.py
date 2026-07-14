# -*- coding: utf-8 -*-
"""
batch_module.py
Chạy nhiều job "dựng draft" song song (giống Batch Studio của VibeCut) - mỗi job độc
lập (media/audio/hiệu ứng riêng), dùng ThreadPoolExecutor để giới hạn số luồng chạy
cùng lúc (tránh quá tải máy khi có hàng chục job).

An toàn song song: mỗi job ghi vào 1 draft_name RIÊNG (thư mục riêng trên đĩa), nên
các luồng không tranh chấp ghi cùng 1 file - đã verify bằng test thật (xem README).

Trạng thái job lưu trong bộ nhớ (dict, không persist qua restart - đây là tool cục bộ
1 người dùng, không cần bền vững qua restart như hệ thống multi-user).
"""

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional

import draft_builder

_batches: Dict[str, "Batch"] = {}
_lock = threading.Lock()


@dataclass
class JobConfig:
    draft_name: str
    media_folder: str
    audio_folder: str
    width: int = 1080
    height: int = 1920
    fps: int = 30
    apply_intro: bool = False
    intro_pool: Optional[List[str]] = None
    apply_transition: bool = False
    transition_pool: Optional[List[str]] = None
    apply_filter: bool = False
    filter_pool: Optional[List[str]] = None
    apply_named_motion: bool = False
    named_motion_pool: Optional[List[str]] = None
    apply_mask: bool = False
    mask_pool: Optional[List[str]] = None


@dataclass
class Job:
    id: str
    config: JobConfig
    status: str = "pending"  # pending -> running -> success | error
    error: Optional[str] = None
    result: Optional[dict] = None
    started_at: Optional[float] = None
    finished_at: Optional[float] = None


@dataclass
class Batch:
    id: str
    jobs: List[Job] = field(default_factory=list)
    parallel_threads: int = 2
    projects_root: str = ""
    _executor: Optional[ThreadPoolExecutor] = None


def _run_single_job(projects_root: str, job: Job):
    job.status = "running"
    job.started_at = time.time()
    try:
        result = draft_builder.build_draft_from_folders(
            projects_root=Path(projects_root),
            draft_name=job.config.draft_name,
            media_folder=Path(job.config.media_folder),
            audio_folder=Path(job.config.audio_folder),
            width=job.config.width,
            height=job.config.height,
            fps=job.config.fps,
            apply_intro=job.config.apply_intro,
            intro_pool=job.config.intro_pool,
            apply_transition=job.config.apply_transition,
            transition_pool=job.config.transition_pool,
            apply_filter=job.config.apply_filter,
            filter_pool=job.config.filter_pool,
            apply_named_motion=job.config.apply_named_motion,
            named_motion_pool=job.config.named_motion_pool,
            apply_mask=job.config.apply_mask,
            mask_pool=job.config.mask_pool,
        )
        job.result = result
        job.status = "success"
    except FileExistsError:
        job.error = f"Draft '{job.config.draft_name}' đã tồn tại - đổi tên khác."
        job.status = "error"
    except Exception as e:
        job.error = str(e)
        job.status = "error"
    finally:
        job.finished_at = time.time()


def start_batch(projects_root: str, job_configs: List[dict], parallel_threads: int = 2) -> str:
    """Tạo 1 batch mới, khởi chạy nền, trả về batch_id để poll trạng thái."""
    batch_id = uuid.uuid4().hex[:12]
    jobs = [Job(id=uuid.uuid4().hex[:8], config=JobConfig(**cfg)) for cfg in job_configs]
    batch = Batch(id=batch_id, jobs=jobs, parallel_threads=max(1, min(4, parallel_threads)),
                   projects_root=projects_root)

    with _lock:
        _batches[batch_id] = batch

    def _run_all():
        executor = ThreadPoolExecutor(max_workers=batch.parallel_threads)
        batch._executor = executor
        futures = [executor.submit(_run_single_job, projects_root, job) for job in jobs]
        for f in futures:
            f.result()  # đợi hết, để biết khi nào batch xong (không raise vì lỗi đã tự bắt trong _run_single_job)
        executor.shutdown(wait=True)

    threading.Thread(target=_run_all, daemon=True).start()
    return batch_id


def get_batch_status(batch_id: str) -> Optional[dict]:
    with _lock:
        batch = _batches.get(batch_id)
    if not batch:
        return None

    jobs_status = []
    counts = {"pending": 0, "running": 0, "success": 0, "error": 0}
    for job in batch.jobs:
        counts[job.status] += 1
        jobs_status.append({
            "id": job.id,
            "draft_name": job.config.draft_name,
            "status": job.status,
            "error": job.error,
            "result": job.result,
        })

    return {
        "batch_id": batch.id,
        "total": len(batch.jobs),
        "counts": counts,
        "jobs": jobs_status,
        "done": counts["success"] + counts["error"] == len(batch.jobs),
    }
