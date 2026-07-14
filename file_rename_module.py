# -*- coding: utf-8 -*-
"""
file_rename_module.py
Sắp xếp file theo thứ tự tuỳ ý + copy đổi tên tuần tự (1.ext, 2.ext...) - giống
"Sắp xếp & Đổi tên File" của VibeCut. Giải quyết đúng gốc rễ: hầu hết module khác của
ZOLO (draft_builder, audio_splitter...) yêu cầu file đặt tên "1.png, 2.png..." theo
đúng thứ tự - tool này làm bước chuẩn bị đó, không cần đổi tên tay trong Explorer.

Luôn COPY (không di chuyển/xoá file gốc) - an toàn, không sợ mất file nếu chọn nhầm
thứ tự, chạy lại được nhiều lần.
"""

import shutil
from pathlib import Path
from typing import List


def rename_and_arrange(file_paths: List[str], output_dir: Path, start_index: int = 1) -> dict:
    """
    Copy từng file trong file_paths (ĐÚNG THỨ TỰ đã cho) vào output_dir, đổi tên thành
    <start_index>.ext, <start_index+1>.ext, ... - giữ nguyên phần mở rộng gốc.

    Trả về {"output_dir", "mapping": [{"original", "new_name"}], "warnings": [...]}
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    warnings = []
    mapping = []

    for i, src_str in enumerate(file_paths):
        src = Path(src_str)
        if not src.exists():
            warnings.append(f"Bỏ qua - không tìm thấy file: {src}")
            continue

        new_name = f"{start_index + i}{src.suffix.lower()}"
        dst = output_dir / new_name

        if dst.exists():
            warnings.append(f"'{new_name}' đã tồn tại trong thư mục đích - đã ghi đè.")

        shutil.copy2(src, dst)
        mapping.append({"original": src.name, "new_name": new_name})

    return {
        "output_dir": str(output_dir),
        "mapping": mapping,
        "warnings": warnings,
        "count": len(mapping),
    }
