# -*- coding: utf-8 -*-
"""
effects_module.py
Gắn hiệu ứng cho segment video NGAY LÚC DỰNG (không sửa được draft đã lưu sau đó -
xem giải thích quan trọng bên dưới).

** GIỚI HẠN QUAN TRỌNG ĐÃ PHÁT HIỆN KHI TEST **
pyJianYingDraft có 2 chế độ:
  - Chế độ tạo mới (VideoSegment vừa `VideoSegment(...)`) -> object đầy đủ, có
    add_animation/add_filter/add_transition/add_keyframe.
  - Chế độ mở draft có sẵn (`DraftFolder.load_template()` -> `ImportedMediaSegment`)
    -> object RÚT GỌN, KHÔNG có các hàm add_* ở trên (chỉ dùng để replace material).

=> Nên KHÔNG THỂ "mở draft đã dựng, rồi gắn hiệu ứng vào sau" như dự tính ban đầu.
   Phải gắn hiệu ứng NGAY khi draft_builder.py tạo từng VideoSegment, TRƯỚC khi
   add_segment() vào track. Module này cung cấp các hàm "decorate" để
   draft_builder.py gọi ngay trong vòng lặp dựng segment.
"""

import random
from typing import List, Literal, Optional

import pyJianYingDraft as jy

# ─── Bộ hiệu ứng mặc định (tên tiếng Trung gốc JianYing, đã XÁC MINH tồn tại thật
#     trong pyJianYingDraft 0.3.0 - chạy list_available() để tự kiểm tra lại nếu
#     nâng cấp version thư viện). resource_id dùng chung hệ ByteDance nên vào CapCut
#     quốc tế vẫn hiện đúng hiệu ứng, chỉ khác tên hiển thị trong code. ───

DEFAULT_INTRO_POOL = ["动感缩小", "向上滑动", "向下滑动", "向左滑动", "向右滑动"]
# dịch: thu nhỏ động cảm / trượt lên / trượt xuống / trượt trái / trượt phải

DEFAULT_TRANSITION_POOL = ["叠加", "压缩", "左移", "右移"]
# dịch: chồng mờ (fade) / nén / trượt trái / trượt phải

DEFAULT_FILTER_POOL = ["原木", "清新", "暖黄"]
# dịch: mộc mạc tự nhiên / trong trẻo tươi mới / vàng ấm

DEFAULT_MASK_POOL = ["圆形", "矩形", "线性"]
# dịch: tròn / chữ nhật / tuyến tính (viền mờ dần) - đã xác minh tồn tại thật


def list_available(category: Literal["intro", "outro", "combo", "transition", "filter", "mask", "named_motion"]) -> List[str]:
    """Liệt kê TẤT CẢ tên hiệu ứng có sẵn trong 1 nhóm - dùng để tự chọn pool khác
    hoặc tự kiểm tra tên còn hợp lệ sau khi nâng cấp thư viện."""
    if category == "named_motion":
        return list(NAMED_MOTION_PRESETS.keys())
    mapping = {
        "intro": jy.IntroType, "outro": jy.OutroType, "combo": jy.GroupAnimationType,
        "transition": jy.TransitionType, "filter": jy.FilterType, "mask": jy.MaskType,
    }
    return [x.name for x in mapping[category]]


def verify_pool(category: str, pool: List[str]) -> List[str]:
    """Trả về danh sách tên KHÔNG hợp lệ trong pool (rỗng = mọi tên đều ổn)."""
    valid = set(list_available(category))
    return [n for n in pool if n not in valid]


def pick_from_pool(pool: List[str], mode: Literal["rotate", "random"], index: int) -> str:
    """Chọn 1 tên từ pool theo vị trí `index` (rotate = lặp vòng tuần tự) hoặc ngẫu nhiên."""
    if mode == "random":
        return random.choice(pool)
    return pool[index % len(pool)]


def decorate_intro(segment: "jy.VideoSegment", animation_name: str, duration_s: float = 0.5):
    """Gắn animation intro cho 1 VideoSegment MỚI TẠO (chưa add_segment)."""
    anim_type = getattr(jy.IntroType, animation_name)
    segment.add_animation(anim_type, duration=jy.trange(0, f"{duration_s}s").duration)


def decorate_transition(segment: "jy.VideoSegment", transition_name: str, duration_s: float = 0.5):
    """Gắn transition (chuyển sang đoạn KẾ TIẾP) cho 1 VideoSegment MỚI TẠO.
    KHÔNG gọi cho đoạn cuối cùng (không có đoạn sau để chuyển tới)."""
    trans_type = getattr(jy.TransitionType, transition_name)
    segment.add_transition(trans_type, duration=jy.trange(0, f"{duration_s}s").duration)


def decorate_filter(segment: "jy.VideoSegment", filter_name: str, intensity: float = 100.0):
    """Gắn filter màu cho 1 VideoSegment MỚI TẠO."""
    filter_type = getattr(jy.FilterType, filter_name)
    segment.add_filter(filter_type, intensity=intensity)


def decorate_ken_burns(segment: "jy.VideoSegment", zoom_from: float = 1.0, zoom_to: float = 1.15):
    """Gắn keyframe zoom nhẹ dần (Ken Burns) cho 1 VideoSegment MỚI TẠO - segment
    phải đã có target_timerange (đã biết duration) trước khi gọi."""
    segment.add_keyframe(jy.KeyframeProperty.uniform_scale, 0, zoom_from)
    segment.add_keyframe(jy.KeyframeProperty.uniform_scale, segment.duration, zoom_to)


# ─── Mở rộng: nhiều kiểu chuyển động hơn Ken Burns cơ bản (zoom/pan/rotate) - đặt tên
#     preset giống VibeCut ("Zoom In", "Zoom Out", "Pan Right"...) - phát hiện được từ
#     docstring còn sót lại trong file add_keyframes_auto.pyc lúc phân tích tool tham khảo. ───

MOTION_PRESETS = ["zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down", "rotate_slight"]


def decorate_motion(segment: "jy.VideoSegment", preset: str, intensity: float = 0.15):
    """
    Gắn 1 trong các kiểu chuyển động cho segment MỚI TẠO (thay thế/mở rộng decorate_ken_burns):
      zoom_in / zoom_out : giống Ken Burns cơ bản
      pan_left / pan_right / pan_up / pan_down : dịch chuyển khung hình ngang/dọc
      rotate_slight       : xoay nhẹ (không quá 5 độ, tránh trông lỗi)

    intensity: mức độ hiệu ứng (0.15 = 15%), áp dụng khác nhau tuỳ preset (zoom: tỉ lệ
    phóng to, pan: tỉ lệ dịch theo % khung hình, rotate: độ xoay tối đa = intensity*30).
    """
    dur = segment.duration
    if preset == "zoom_in":
        segment.add_keyframe(jy.KeyframeProperty.uniform_scale, 0, 1.0)
        segment.add_keyframe(jy.KeyframeProperty.uniform_scale, dur, 1.0 + intensity)
    elif preset == "zoom_out":
        segment.add_keyframe(jy.KeyframeProperty.uniform_scale, 0, 1.0 + intensity)
        segment.add_keyframe(jy.KeyframeProperty.uniform_scale, dur, 1.0)
    elif preset == "pan_left":
        segment.add_keyframe(jy.KeyframeProperty.uniform_scale, 0, 1.0 + intensity)  # phóng nhẹ để có chỗ pan
        segment.add_keyframe(jy.KeyframeProperty.position_x, 0, intensity / 2)
        segment.add_keyframe(jy.KeyframeProperty.position_x, dur, -intensity / 2)
    elif preset == "pan_right":
        segment.add_keyframe(jy.KeyframeProperty.uniform_scale, 0, 1.0 + intensity)
        segment.add_keyframe(jy.KeyframeProperty.position_x, 0, -intensity / 2)
        segment.add_keyframe(jy.KeyframeProperty.position_x, dur, intensity / 2)
    elif preset == "pan_up":
        segment.add_keyframe(jy.KeyframeProperty.uniform_scale, 0, 1.0 + intensity)
        segment.add_keyframe(jy.KeyframeProperty.position_y, 0, -intensity / 2)
        segment.add_keyframe(jy.KeyframeProperty.position_y, dur, intensity / 2)
    elif preset == "pan_down":
        segment.add_keyframe(jy.KeyframeProperty.uniform_scale, 0, 1.0 + intensity)
        segment.add_keyframe(jy.KeyframeProperty.position_y, 0, intensity / 2)
        segment.add_keyframe(jy.KeyframeProperty.position_y, dur, -intensity / 2)
    elif preset == "rotate_slight":
        angle = intensity * 30  # intensity=0.15 -> 4.5 độ, đủ nhẹ để không trông lỗi
        segment.add_keyframe(jy.KeyframeProperty.rotation, 0, -angle / 2)
        segment.add_keyframe(jy.KeyframeProperty.rotation, dur, angle / 2)
    else:
        raise ValueError(f"Preset chuyển động không hợp lệ: {preset}. Chọn trong {MOTION_PRESETS}")


def decorate_mask(segment: "jy.VideoSegment", mask_name: str, size: float = 0.8,
                   feather: float = 0.1, round_corner: Optional[float] = None):
    """Gắn mask (khung hình dạng tròn/tim/sao/chữ nhật bo góc...) cho 1 VideoSegment MỚI TẠO."""
    mask_type = getattr(jy.MaskType, mask_name)
    segment.add_mask(mask_type, size=size, feather=feather, round_corner=round_corner)


# ─── Keyframe Lab: bộ preset chuyển động đặt tên sẵn phong phú hơn (lấy cảm hứng từ
#     danh sách preset của VibeCut - Cinematic Push, Orbital, Heartbeat Pulse...) ───
#
# Định nghĩa DẠNG KHAI BÁO: mỗi preset = list các (property, [(tỉ_lệ_thời_gian, giá_trị), ...]).
# Áp dụng bằng apply_named_motion() - gọi add_keyframe() nhiều lần theo đúng tỉ lệ thời
# gian thật của segment (đã test: pyJianYingDraft nhận nhiều keyframe/property, không
# giới hạn 2 điểm như code cũ).

NAMED_MOTION_PRESETS = {
    # (tỉ_lệ 0.0-1.0, giá_trị) - tỉ lệ sẽ nhân với duration thật của segment lúc áp dụng
    "fade_in": {
        "alpha": [(0.0, 0.0), (1.0, 1.0)],
    },
    "slight_rotate": {
        "rotation": [(0.0, -1.5), (0.2, 1.0), (0.4, -1.0), (0.6, 1.5), (0.8, -1.0), (1.0, 0.0)],
    },
    "ken_burns_classic": {
        "uniform_scale": [(0.0, 1.0), (1.0, 1.18)],
        "position_x": [(0.0, 0.0), (1.0, 0.04)],
        "position_y": [(0.0, 0.0), (1.0, -0.03)],
    },
    "cinematic_push": {
        "uniform_scale": [(0.0, 1.0), (0.3, 1.03), (0.6, 1.08), (1.0, 1.15)],
        "position_y": [(0.0, 0.01), (1.0, -0.01)],
    },
    "dramatic_reveal": {
        "uniform_scale": [(0.0, 1.35), (0.5, 1.15), (1.0, 1.0)],
        "alpha": [(0.0, 0.3), (0.3, 1.0), (1.0, 1.0)],
    },
    "orbital": {
        # xấp xỉ quỹ đạo tròn quanh tâm bằng 6 điểm (không có bezier thật, nội suy tuyến tính)
        "position_x": [(0.0, 0.0), (0.17, 0.04), (0.33, 0.04), (0.5, 0.0), (0.67, -0.04), (0.83, -0.04), (1.0, 0.0)],
        "position_y": [(0.0, -0.04), (0.17, -0.02), (0.33, 0.02), (0.5, 0.04), (0.67, 0.02), (0.83, -0.02), (1.0, -0.04)],
    },
    "heartbeat_pulse": {
        "uniform_scale": [(0.0, 1.0), (0.1, 1.06), (0.2, 1.0), (0.3, 1.06), (0.4, 1.0),
                           (0.55, 1.06), (0.65, 1.0), (0.8, 1.06), (0.9, 1.0), (1.0, 1.0)],
    },
    "parallax_drift": {
        "position_x": [(0.0, -0.03), (0.25, -0.015), (0.5, 0.0), (0.75, 0.015), (1.0, 0.03)],
        "uniform_scale": [(0.0, 1.08), (1.0, 1.12)],
    },
    "spiral_zoom": {
        "uniform_scale": [(0.0, 1.0), (0.33, 1.06), (0.67, 1.12), (1.0, 1.2)],
        "rotation": [(0.0, 0.0), (0.33, 4.0), (0.67, 8.0), (1.0, 12.0)],
    },
    "whip_shake": {
        "position_x": [(0.0, 0.0), (0.1, 0.03), (0.2, -0.03), (0.3, 0.025), (0.4, -0.025),
                        (0.5, 0.015), (0.6, -0.015), (0.7, 0.01), (0.8, -0.01), (0.9, 0.005), (1.0, 0.0)],
    },
    "breathing_focus": {
        "uniform_scale": [(0.0, 1.0), (0.22, 1.05), (0.5, 1.0), (0.78, 1.05), (1.0, 1.0)],
        "brightness": [(0.0, 0.0), (0.5, 0.05), (1.0, 0.0)],
    },
    "epicenter": {
        "uniform_scale": [(0.0, 1.3), (0.25, 1.15), (0.5, 1.05), (0.75, 1.0), (1.0, 1.0)],
        "contrast": [(0.0, 0.1), (0.3, 0.0), (1.0, 0.0)],
    },
    "tilt_shift_motion": {
        # pyJianYingDraft không hỗ trợ blur quang học thật (tilt-shift cần shader riêng
        # của CapCut) - đây là XẤP XỈ bằng chuyển động nhẹ, KHÔNG có hiệu ứng mờ nền.
        "uniform_scale": [(0.0, 1.0), (0.5, 1.04), (1.0, 1.0)],
        "position_y": [(0.0, -0.015), (0.5, 0.0), (1.0, 0.015)],
    },
}

_PROPERTY_MAP = {
    "position_x": "position_x", "position_y": "position_y", "rotation": "rotation",
    "uniform_scale": "uniform_scale", "alpha": "alpha", "saturation": "saturation",
    "contrast": "contrast", "brightness": "brightness",
}


def apply_named_motion(segment: "jy.VideoSegment", preset_name: str):
    """
    Gắn 1 preset chuyển động đặt tên sẵn (nhiều keyframe/property) cho VideoSegment
    MỚI TẠO. Xem NAMED_MOTION_PRESETS phía trên để biết danh sách + preview logic.
    """
    if preset_name not in NAMED_MOTION_PRESETS:
        raise ValueError(f"Preset '{preset_name}' không tồn tại. Chọn trong: {list(NAMED_MOTION_PRESETS)}")

    dur = segment.duration
    preset = NAMED_MOTION_PRESETS[preset_name]
    for prop_name, points in preset.items():
        kf_property = getattr(jy.KeyframeProperty, _PROPERTY_MAP[prop_name])
        for frac, value in points:
            segment.add_keyframe(kf_property, int(frac * dur), value)
