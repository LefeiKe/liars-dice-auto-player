"""固定 2560×1369 界面布局的识别与自动点击。

本模块只使用本地屏幕像素判断状态。所有坐标均按参考分辨率归一化，
因此在游戏全屏分辨率改变时仍可按比例换算；界面比例发生改变时则需调整坐标。
"""

from __future__ import annotations

import ctypes
import os
import random
import subprocess
import sys
import time
from dataclasses import dataclass

import cv2
import mss
import numpy as np
import pyautogui
import pydirectinput
from PIL import Image, ImageDraw, ImageFont

from calibrator import RegionSelector
from config_manager import BASE_DIR
from screen_capture import ScreenCapture


REFERENCE_WIDTH = 2560
REFERENCE_HEIGHT = 1369

# 参考截图中的按钮中心坐标。
QUANTITY_10 = (1162, 1172)
DICE_POINTS = (
    (1513, 1101),
    (1623, 1101),
    (1730, 1101),
    (1513, 1208),
    (1623, 1208),
    (1730, 1208),
)
BID_BUTTON = (1628, 891)
FORCE_OPEN_BUTTON = (2016, 891)
PLAY_AGAIN_BUTTON = (2244, 1275)

# 用于判断界面和按钮状态的局部区域，格式为 x1、y1、x2、y2。
BID_PANEL_ROI = (606, 985, 1960, 1329)
BID_BUTTON_ROI = (1550, 808, 1718, 979)
FORCE_OPEN_ROI = (1930, 806, 2106, 981)
PLAY_AGAIN_ROI = (2012, 1217, 2473, 1331)
RESULT_PANEL_ROI = (1524, 440, 2475, 1341)

# 文字模板搜索范围。每帧先缩放回参考分辨率，再在这些范围中匹配字形。
BID_TEXT_ROI = (1480, 760, 1780, 1010)
FORCE_OPEN_TEXT_ROI = (1880, 760, 2170, 1010)
PLAY_AGAIN_TEXT_ROI = (2050, 1160, 2480, 1360)
TEXT_TEMPLATE_DIR = BASE_DIR / "text_templates"
TEXT_CROPS = {
    # 仅保留按钮截图中的文字部分，减少背景动画和按钮颜色的影响。
    "force_open.png": (35, 48, 150, 135),
    "bid.png": (40, 50, 165, 145),
    "play_again.png": (165, 25, 415, 108),
}
DEBUG_WINDOW_ID = "GameAutoPlayerStatus"
DEBUG_WINDOW_TITLE = "逆水寒大话骰连点器"
SELECTION_CONSOLE_SCRIPT = BASE_DIR / "selection_console.py"


def _load_chinese_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """优先使用 Windows 自带微软雅黑，保证 OpenCV 窗口可以显示中文。"""
    font_paths = (
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/simhei.ttf",
    )
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _set_unicode_window_title(window_id: str, chinese_title: str) -> None:
    """绕过 OpenCV 的 ANSI 标题接口，使用 Windows Unicode API 设置标题。"""
    try:
        window_handle = ctypes.windll.user32.FindWindowW(None, window_id)
        if window_handle:
            ctypes.windll.user32.SetWindowTextW(window_handle, chinese_title)
    except (AttributeError, OSError):
        pass


def _debug_window_is_closed() -> bool:
    """检测用户是否点击了信息窗口右上角的关闭按钮。"""
    try:
        return (
            cv2.getWindowProperty(DEBUG_WINDOW_ID, cv2.WND_PROP_VISIBLE) < 1
        )
    except cv2.error:
        return True


def _focus_selected_game_window(geometry: "ScreenGeometry") -> None:
    """将框选区域中心所在的游戏窗口切到前台，避免首个点击仅用于激活窗口。"""
    try:
        class Point(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        point = Point(
            geometry.left + geometry.width // 2,
            geometry.top + geometry.height // 2,
        )
        window_handle = ctypes.windll.user32.WindowFromPoint(point)
        if window_handle:
            ctypes.windll.user32.SetForegroundWindow(window_handle)
    except (AttributeError, OSError):
        pass


def _prepare_console_instructions() -> int:
    """在当前 CMD 中输出说明，并返回控制台窗口句柄。"""
    os.system("chcp 65001 >nul")
    os.system("mode con cols=78 lines=18")
    os.system("cls")
    try:
        ctypes.windll.kernel32.SetConsoleTitleW("逆水寒大话骰连点器 - 框选说明")
    except (AttributeError, OSError):
        pass
    print("逆水寒大话骰连点器")
    print()
    print("请正好框选完整的游戏画面。")
    print()
    print("1. 框选范围贴合游戏内容的四条边缘。")
    print("2. 不要包含窗口标题栏和窗口边框。")
    print("3. 不要包含黑边、桌面或其他窗口。")
    print("4. 全屏模式请框选整个游戏画面。")
    print()
    print("退出程序：Esc")
    try:
        return int(ctypes.windll.kernel32.GetConsoleWindow())
    except (AttributeError, OSError):
        return 0


def _hide_console(console_handle: int) -> None:
    if not console_handle:
        return
    try:
        ctypes.windll.user32.ShowWindow(console_handle, 0)
    except (AttributeError, OSError):
        pass


def _show_console_as_click_through_overlay(console_handle: int) -> None:
    """将 CMD 显示为置顶、实色且鼠标穿透的框选说明层。"""
    if not console_handle:
        return
    try:
        user32 = ctypes.windll.user32
        get_window_long = user32.GetWindowLongW
        set_window_long = user32.SetWindowLongW
        extended_style = get_window_long(console_handle, -20)
        # 仅启用 WS_EX_TRANSPARENT，让鼠标事件穿透；移除透明图层样式。
        set_window_long(
            console_handle,
            -20,
            (extended_style | 0x00000020) & ~0x00080000,
        )
        # HWND_TOPMOST，显示但不激活，避免抢走框选界面的键盘焦点。
        user32.SetWindowPos(
            console_handle,
            -1,
            20,
            20,
            720,
            350,
            0x0010 | 0x0040,
        )
        user32.ShowWindow(console_handle, 4)
    except (AttributeError, OSError):
        pass


def _launch_selection_console() -> subprocess.Popen | None:
    """创建一个独立可见的控制台显示说明，避免 Windows Terminal 隐藏原 CMD。"""
    try:
        return subprocess.Popen(
            [sys.executable, str(SELECTION_CONSOLE_SCRIPT)],
            creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0x00000010),
        )
    except OSError as error:
        print(f"无法打开框选说明控制台：{error}")
        return None


@dataclass
class ScreenGeometry:
    left: int
    top: int
    width: int
    height: int

    def point(self, reference: tuple[int, int]) -> tuple[int, int]:
        """将参考截图坐标换算为当前主显示器坐标。"""
        return (
            self.left + round(reference[0] * self.width / REFERENCE_WIDTH),
            self.top + round(reference[1] * self.height / REFERENCE_HEIGHT),
        )

    def roi(self, reference: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        x1, y1 = self.point((reference[0], reference[1]))
        x2, y2 = self.point((reference[2], reference[3]))
        return x1 - self.left, y1 - self.top, x2 - self.left, y2 - self.top


@dataclass
class TextMatch:
    score: float
    center: tuple[int, int]
    scale: float


def _crop(frame: np.ndarray, geometry: ScreenGeometry, roi) -> np.ndarray:
    x1, y1, x2, y2 = geometry.roi(roi)
    return frame[max(0, y1) : max(1, y2), max(0, x1) : max(1, x2)]


def _hsv_ratio(image: np.ndarray, lower, upper) -> float:
    """返回图像中指定 HSV 色彩范围所占比例。"""
    if image.size == 0:
        return 0.0
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array(lower), np.array(upper))
    return float(cv2.countNonZero(mask) / mask.size)


def _purple_ratio(image: np.ndarray) -> float:
    return _hsv_ratio(image, (120, 35, 35), (170, 255, 255))


def _blue_ratio(image: np.ndarray) -> float:
    # 蓝色可用按钮包含大面积高亮蓝/青色，灰白禁用按钮的饱和度较低。
    return _hsv_ratio(image, (85, 45, 70), (130, 255, 255))


def _yellow_ratio(image: np.ndarray) -> float:
    return _hsv_ratio(image, (15, 45, 100), (42, 255, 255))


def _bright_button_ratio(image: np.ndarray) -> float:
    """检测强开按钮内部接近白色的高亮纹理，排除普通蓝紫背景。"""
    return _hsv_ratio(image, (0, 0, 180), (179, 105, 255))


def _load_text_template(filename: str) -> np.ndarray:
    """读取按钮截图并裁出文字本身。"""
    image = cv2.imread(str(TEXT_TEMPLATE_DIR / filename), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise RuntimeError(f"缺少文字模板：{TEXT_TEMPLATE_DIR / filename}")
    x1, y1, x2, y2 = TEXT_CROPS[filename]
    return image[y1:y2, x1:x2]


def _load_full_button_template(filename: str) -> np.ndarray:
    """读取包含按钮轮廓的完整模板，用于先定位按钮所在位置。"""
    image = cv2.imread(str(TEXT_TEMPLATE_DIR / filename), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise RuntimeError(f"缺少按钮模板：{TEXT_TEMPLATE_DIR / filename}")
    return image


def _text_match_score(
    reference_frame: np.ndarray,
    roi: tuple[int, int, int, int],
    template_gray: np.ndarray,
) -> float:
    """在指定范围进行多尺度字形搜索，返回 0 到 1 的匹配分数。"""
    x1, y1, x2, y2 = roi
    search_gray = cv2.cvtColor(
        reference_frame[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY
    )
    search_edges = cv2.Canny(search_gray, 60, 160)
    best = 0.0
    # 独立按钮截图与完整截图可能存在少量缩放差异，因此尝试多个尺度。
    for scale in np.linspace(0.60, 1.35, 16):
        scaled = cv2.resize(
            template_gray,
            None,
            fx=float(scale),
            fy=float(scale),
            interpolation=cv2.INTER_LINEAR,
        )
        template_edges = cv2.Canny(scaled, 60, 160)
        if (
            search_edges.shape[0] < template_edges.shape[0]
            or search_edges.shape[1] < template_edges.shape[1]
        ):
            continue
        result = cv2.matchTemplate(
            search_edges, template_edges, cv2.TM_CCOEFF_NORMED
        )
        best = max(best, float(cv2.minMaxLoc(result)[1]))
    return float(np.clip(best, 0.0, 1.0))


def _find_text(
    frame: np.ndarray,
    template_gray: np.ndarray,
    search_band: tuple[float, float, float, float],
    expected_scale: float,
) -> TextMatch:
    """在原始画面中多尺度搜索文字，不拉伸画面，因此兼容不同宽高比。"""
    height, width = frame.shape[:2]
    x1 = int(width * search_band[0])
    y1 = int(height * search_band[1])
    x2 = int(width * search_band[2])
    y2 = int(height * search_band[3])
    search = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
    # 大画面先缩小后搜索，显著降低全宽多尺度匹配的耗时。
    processing_scale = min(
        1.0,
        1280.0 / max(1, search.shape[1]),
        800.0 / max(1, search.shape[0]),
    )
    if processing_scale < 1.0:
        search = cv2.resize(
            search,
            None,
            fx=processing_scale,
            fy=processing_scale,
            interpolation=cv2.INTER_AREA,
        )
    search_edges = cv2.Canny(search, 60, 160)
    best = TextMatch(0.0, (0, 0), expected_scale)

    # UI 在宽屏、窄屏和窗口模式下可能按宽度或高度缩放。
    # 使用更宽的尺度范围，不假定某一种固定窗口比例。
    factors = sorted(set(np.linspace(0.45, 1.75, 21).tolist() + [1.0]))
    for factor in factors:
        scale = max(0.12, expected_scale * float(factor) * processing_scale)
        scaled = cv2.resize(
            template_gray,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_LINEAR,
        )
        edges = cv2.Canny(scaled, 60, 160)
        if edges.shape[0] >= search_edges.shape[0] or edges.shape[1] >= search_edges.shape[1]:
            continue
        result = cv2.matchTemplate(search_edges, edges, cv2.TM_CCOEFF_NORMED)
        _min_value, max_value, _min_location, max_location = cv2.minMaxLoc(result)
        if max_value > best.score:
            best = TextMatch(
                float(max_value),
                (
                    x1 + round(
                        (max_location[0] + edges.shape[1] // 2)
                        / processing_scale
                    ),
                    y1 + round(
                        (max_location[1] + edges.shape[0] // 2)
                        / processing_scale
                    ),
                ),
                scale / processing_scale,
            )
    return best


def _local_color_ratio(
    frame: np.ndarray,
    center: tuple[int, int],
    half_size: tuple[int, int],
    lower,
    upper,
) -> float:
    """在识别文字周围检测按钮颜色或高亮。"""
    x, y = center
    half_width, half_height = half_size
    crop = frame[
        max(0, y - half_height) : min(frame.shape[0], y + half_height),
        max(0, x - half_width) : min(frame.shape[1], x + half_width),
    ]
    return _hsv_ratio(crop, lower, upper)


def _find_wide_yellow_button(frame: np.ndarray) -> tuple[int, int] | None:
    """寻找画面下半部宽而扁的黄色按钮，用于定位“再来一局”。"""
    height, width = frame.shape[:2]
    y_offset = height // 2
    lower_half = frame[y_offset:, :]
    hsv = cv2.cvtColor(lower_half, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(
        hsv,
        np.array((15, 45, 100)),
        np.array((42, 255, 255)),
    )
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (11, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _hierarchy = cv2.findContours(
        mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    candidates: list[tuple[float, tuple[int, int]]] = []
    minimum_area = width * height * 0.002
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        center_x = x + w // 2
        center_y = y_offset + y + h // 2
        if (
            h <= 0
            or w / h < 2.2
            or w * h < minimum_area
            or center_x < width * 0.50
            or center_y < height * 0.70
        ):
            continue
        candidates.append((float(w * h), (center_x, center_y)))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def _click(geometry: ScreenGeometry, point: tuple[int, int]) -> None:
    """移动鼠标并用 DirectInput 发送真实按下/抬起事件。"""
    x, y = geometry.point(point)
    pyautogui.moveTo(
	x=x,
	y=y,
	duration=random.uniform(0.2, 0.8),
	tween=pyautogui.easeInOutQuad
    )
    pydirectinput.mouseDown(button="left")
    time.sleep(0.06)
    pydirectinput.mouseUp(button="left")


def _click_local(geometry: ScreenGeometry, point: tuple[int, int]) -> None:
    """点击框选游戏画面内部的实际识别坐标。"""
    _focus_selected_game_window(geometry)
    time.sleep(0.15)
    x = geometry.left + int(point[0])
    y = geometry.top + int(point[1])
    pyautogui.moveTo(
	x=x,
	y=y,
	duration=random.uniform(0.2, 0.8),
	tween=pyautogui.easeInOutQuad
    )
    pydirectinput.mouseDown(button="left")
    time.sleep(0.06)
    pydirectinput.mouseUp(button="left")


def _make_panel(
    state: str,
    bid_panel: float,
    bid_text: float,
    bid_yellow: float,
    force_text: float,
    force_frames: int,
    replay_text: float,
    replay_frames: int,
    bid_locked: bool,
    chosen_point: int | None,
    completed_rounds: int,
    paused: bool,
) -> np.ndarray:
    total_money_w = completed_rounds * 3.6
    money_text = f"{total_money_w:g}w"
    lines = [
        ("逆水寒大话骰连点器", (235, 235, 235)),
        (f"当前状态：{state}", (80, 220, 100)),
        (f"运行状态：{'已暂停' if paused else '运行中'}", (80, 190, 255)),
        (f"已获取交子（仅供参考）：{money_text}", (255, 215, 80)),
        (f"识别到叫骰面板：{'是' if bid_panel > 0.35 else '否'}", (220, 220, 220)),
        (f"识别到“叫骰”文字：{'是' if bid_text > 0.42 else '否'}", (220, 220, 220)),
        (f"叫骰按钮黄色：{'是' if bid_yellow > 0.30 else '否'}", (220, 220, 220)),
        (
            f"识别到“强开”：{'是' if force_frames > 0 else '否'}"
            f"（连续 {force_frames}/3 帧）",
            (220, 220, 220),
        ),
        (
            f"识别到“再来一局”：{'是' if replay_frames > 0 else '否'}"
            f"（连续 {replay_frames}/3 帧）",
            (220, 220, 220),
        ),
        (f"叫骰操作锁定：{'是' if bid_locked else '否'}", (220, 220, 220)),
        (f"当前选择：数量10，点数{chosen_point or '未选择'}", (220, 220, 220)),
        ("暂停/继续：双击本窗口；退出：Esc 或右上角 ×", (80, 190, 255)),
    ]
    panel = np.full((488, 760, 3), 27, dtype=np.uint8)
    image = Image.fromarray(cv2.cvtColor(panel, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(image)
    normal_font = _load_chinese_font(19)
    title_font = _load_chinese_font(23)
    for index, (text, color) in enumerate(lines):
        draw.text(
            (18, 14 + index * 38),
            text,
            font=title_font if index == 0 else normal_font,
            fill=(color[2], color[1], color[0]),
        )
    return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)


def run_auto_player() -> None:
    """按用户规则执行识别和点击，优先级：再来一局 > 强开 > 叫骰。"""
    pyautogui.PAUSE = 0.04
    pyautogui.FAILSAFE = False
    pydirectinput.PAUSE = 0.04

    # 每次启动都由用户框选完整游戏画面。后续坐标全部相对于此框换算，
    # 因而同一套参考布局可用于窗口化、无边框和全屏模式。
    # 隐藏启动脚本原有控制台，再截取干净桌面。
    original_console_handle = _prepare_console_instructions()
    _hide_console(original_console_handle)
    time.sleep(0.08)
    with ScreenCapture() as desktop_capture:
        desktop, origin = desktop_capture.capture_all_monitors()
    selector = RegionSelector(
        desktop,
        origin,
        "完整游戏画面（请贴合游戏内容边缘）",
    )
    instruction_process = _launch_selection_console()
    selected = selector.show()
    if instruction_process is not None:
        instruction_process.terminate()
        try:
            instruction_process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            instruction_process.kill()
    if selected is None:
        print("已取消游戏画面框选，程序未启动。")
        return

    geometry = ScreenGeometry(
        int(selected["left"]),
        int(selected["top"]),
        int(selected["width"]),
        int(selected["height"]),
    )
    selected_ratio = geometry.width / geometry.height
    reference_ratio = REFERENCE_WIDTH / REFERENCE_HEIGHT
    if abs(selected_ratio - reference_ratio) / reference_ratio > 0.04:
        print(
            "提示：框选区域的宽高比与参考画面相差较大，"
            "请确认没有包含窗口边框、黑边或桌面区域。"
        )

    selection_done = False
    selection_attempts = 0
    selection_attempt_time = 0.0
    chosen_point: int | None = None
    last_action = 0.0
    force_frames = 0
    replay_frames = 0
    bid_panel_frames = 0
    panel_absent_frames = 0
    bid_locked = False
    force_latched = False
    replay_latched = False
    replay_pending_confirmation = False
    replay_absent_frames = 0
    replay_attempts = 0
    replay_click_time = 0.0
    completed_rounds = 0
    state = "等待可识别界面"
    bid_template = _load_text_template("bid.png")
    bid_button_template = _load_full_button_template("bid.png")
    force_template = _load_text_template("force_open.png")
    replay_template = _load_text_template("play_again.png")
    start_template = _load_full_button_template("start.png")
    control = {"paused": False}

    try:
        with mss.mss() as capture:
            monitor = {
                "left": geometry.left,
                "top": geometry.top,
                "width": geometry.width,
                "height": geometry.height,
            }

            # OpenCV 的内部窗口名保持 ASCII，避免 Windows 标题栏中文乱码。
            cv2.namedWindow(DEBUG_WINDOW_ID, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(DEBUG_WINDOW_ID, 760, 450)
            cv2.setWindowProperty(
                DEBUG_WINDOW_ID, cv2.WND_PROP_TOPMOST, 1
            )
            _set_unicode_window_title(DEBUG_WINDOW_ID, DEBUG_WINDOW_TITLE)

            def _handle_debug_mouse(
                event: int,
                _x: int,
                _y: int,
                _flags: int,
                _parameter: object,
            ) -> None:
                if event == cv2.EVENT_LBUTTONDBLCLK:
                    control["paused"] = not control["paused"]

            cv2.setMouseCallback(DEBUG_WINDOW_ID, _handle_debug_mouse)

            while True:
                bgra = np.asarray(capture.grab(monitor))
                frame = cv2.cvtColor(bgra, cv2.COLOR_BGRA2BGR)

                # 游戏通常按较受限制的一边缩放 UI，不能只根据窗口高度推算。
                expected_scale = min(
                    geometry.width / REFERENCE_WIDTH,
                    geometry.height / REFERENCE_HEIGHT,
                )
                # 先用完整圆形按钮定位，再只在按钮附近确认“叫骰”文字。
                bid_button_match = _find_text(
                    frame,
                    bid_button_template,
                    (0.00, 0.35, 1.00, 1.00),
                    expected_scale,
                )
                if bid_button_match.score > 0.27:
                    bid_x, bid_y = bid_button_match.center
                    bid_margin_x = max(75, round(145 * expected_scale))
                    bid_margin_y = max(75, round(145 * expected_scale))
                    bid_text_band = (
                        max(0.0, (bid_x - bid_margin_x) / geometry.width),
                        max(0.0, (bid_y - bid_margin_y) / geometry.height),
                        min(1.0, (bid_x + bid_margin_x) / geometry.width),
                        min(1.0, (bid_y + bid_margin_y) / geometry.height),
                    )
                    bid_text_match = _find_text(
                        frame, bid_template, bid_text_band, expected_scale
                    )
                    bid_match = bid_button_match
                else:
                    bid_text_match = TextMatch(0.0, (0, 0), expected_scale)
                    bid_match = bid_button_match
                force_match = _find_text(
                    frame, force_template, (0.00, 0.35, 1.00, 1.00), expected_scale
                )
                replay_button_center = _find_wide_yellow_button(frame)
                if replay_button_center is not None:
                    replay_x, replay_y = replay_button_center
                    margin_x = max(180, round(360 * expected_scale))
                    margin_y = max(80, round(150 * expected_scale))
                    replay_band = (
                        max(0.0, (replay_x - margin_x) / geometry.width),
                        max(0.0, (replay_y - margin_y) / geometry.height),
                        min(1.0, (replay_x + margin_x) / geometry.width),
                        min(1.0, (replay_y + margin_y) / geometry.height),
                    )
                    replay_match = _find_text(
                        frame, replay_template, replay_band, expected_scale
                    )
                    start_match = _find_text(
                        frame,
                        start_template,
                        replay_band,
                        expected_scale,
                    )
                else:
                    replay_match = TextMatch(0.0, (0, 0), expected_scale)
                    start_match = TextMatch(0.0, (0, 0), expected_scale)
                bid_text = bid_text_match.score
                force_text = force_match.score
                replay_text = replay_match.score

                bid_panel = _local_color_ratio(
                    frame,
                    (
                        round(bid_match.center[0] - 250 * expected_scale),
                        round(bid_match.center[1] + 220 * expected_scale),
                    ),
                    (
                        round(650 * expected_scale),
                        round(180 * expected_scale),
                    ),
                    (120, 35, 35),
                    (170, 255, 255),
                )

                bid_yellow = _local_color_ratio(
                    frame,
                    bid_match.center,
                    (round(90 * expected_scale), round(90 * expected_scale)),
                    (15, 45, 100),
                    (42, 255, 255),
                )
                force_bright = _local_color_ratio(
                    frame,
                    force_match.center,
                    (round(85 * expected_scale), round(85 * expected_scale)),
                    (0, 0, 180),
                    (179, 105, 255),
                )
                replay_yellow = 1.0 if replay_button_center is not None else 0.0
                # 文字与按钮外观必须同时成立，避免背景偶然形成相似字形。
                if force_text > 0.42 and force_bright > 0.30:
                    force_frames = min(force_frames + 1, 3)
                else:
                    force_frames = 0
                    force_latched = False
                if (
                    replay_text > 0.38
                    and start_match.score < 0.40
                    and replay_yellow > 0.30
                ):
                    replay_frames = min(replay_frames + 1, 3)
                    replay_absent_frames = 0
                else:
                    replay_frames = 0
                    replay_latched = False
                    if replay_pending_confirmation:
                        screen_changed = (
                            replay_button_center is None
                            or start_match.score > 0.40
                        )
                        replay_absent_frames = (
                            min(replay_absent_frames + 1, 3)
                            if screen_changed
                            else 0
                        )
                        # 连续三帧离开结算按钮后，才确认本局完成并增加交子。
                        if replay_absent_frames >= 3:
                            completed_rounds += 1
                            replay_pending_confirmation = False
                            replay_attempts = 0

                if bid_panel > 0.35 and bid_text > 0.42:
                    bid_panel_frames = min(bid_panel_frames + 1, 5)
                    panel_absent_frames = 0
                else:
                    bid_panel_frames = 0
                    panel_absent_frames = min(panel_absent_frames + 1, 6)
                    # 只有面板稳定消失后才允许开始下一轮，忽略单帧动画闪烁。
                    if panel_absent_frames >= 6:
                        bid_locked = False
                        selection_done = False
                        selection_attempts = 0

                now = time.monotonic()
                action_ready = now - last_action >= 1.0

                # 连续识别到“再来一局”字形后点击，避免背景颜色误判。
                if replay_frames >= 3:
                    state = "检测到结束界面"
                    selection_done = False
                    bid_locked = True
                    if (
                        action_ready
                        and (
                            not replay_latched
                            or (
                                replay_pending_confirmation
                                and now - replay_click_time >= 1.5
                            )
                        )
                        and replay_attempts < 3
                        and not control["paused"]
                    ):
                        _click_local(geometry, replay_button_center)
                        last_action = now
                        replay_click_time = time.monotonic()
                        replay_latched = True
                        replay_pending_confirmation = True
                        replay_attempts += 1
                        state = "已点击再来一局"
                    elif replay_pending_confirmation and replay_attempts >= 3:
                        state = "再来一局连续3次未生效，请检查游戏焦点"

                # 必须连续三帧识别到“强开”字形才允许点击。
                elif force_frames >= 3:
                    state = "检测到强开按钮"
                    selection_done = False
                    bid_locked = True
                    if (
                        action_ready
                        and not force_latched
                        and not control["paused"]
                    ):
                        _click_local(geometry, force_match.center)
                        last_action = now
                        force_latched = True
                        state = "已点击强开"

                # 下方紫色叫骰面板出现后，先选择 10 和一个随机点数。
                elif (
                    bid_panel_frames >= 5
                    and not bid_locked
                    and not control["paused"]
                ):
                    if not selection_done and action_ready:
                        chosen_point = random.randint(1, 6)
                        # 数量和点数相对于实际识别到的叫骰按钮定位。
                        ui_scale = max(0.20, bid_match.scale)
                        quantity_point = (
                            round(bid_match.center[0] - 466 * ui_scale),
                            round(bid_match.center[1] + 281 * ui_scale),
                        )
                        dice_offsets = (
                            (-115, 210),
                            (-5, 210),
                            (102, 210),
                            (-115, 317),
                            (-5, 317),
                            (102, 317),
                        )
                        dice_point = (
                            round(
                                bid_match.center[0]
                                + dice_offsets[chosen_point - 1][0] * ui_scale
                            ),
                            round(
                                bid_match.center[1]
                                + dice_offsets[chosen_point - 1][1] * ui_scale
                            ),
                        )
                        _focus_selected_game_window(geometry)
                        time.sleep(0.18)
                        _click_local(geometry, quantity_point)
                        # 等待数量控件完成状态切换后，再选择点数。
                        time.sleep(random.uniform(0.0, 2.0))
                        if control["paused"]:
                            state = "已暂停"
                            continue
                        _click_local(geometry, dice_point)
                        selection_done = True
                        selection_attempts += 1
                        selection_attempt_time = time.monotonic()
                        last_action = time.monotonic()
                        state = (
                            f"已尝试选择 10 个、{chosen_point} 点"
                            f"（第{selection_attempts}/3次）"
                        )
                    elif (
                        selection_done
                        and bid_text > 0.42
                        and bid_yellow > 0.30
                        and action_ready
                    ):
                        _click_local(geometry, bid_match.center)
                        last_action = now
                        selection_done = False
                        bid_locked = True
                        selection_attempts = 0
                        state = "已点击叫骰"
                    elif (
                        selection_done
                        and bid_yellow <= 0.30
                        and time.monotonic() - selection_attempt_time >= 1.5
                    ):
                        if selection_attempts < 3:
                            selection_done = False
                            state = "选择未生效，准备重试"
                        else:
                            state = "选择连续3次未生效，请检查游戏焦点"
                    else:
                        state = "等待叫骰按钮变黄"
                else:
                    state = "等待可识别界面"

                if control["paused"]:
                    state = "已暂停"

                cv2.imshow(
                    DEBUG_WINDOW_ID,
                    _make_panel(
                        state,
                        bid_panel,
                        bid_text,
                        bid_yellow,
                        force_text,
                        force_frames,
                        replay_text,
                        replay_frames,
                        bid_locked,
                        chosen_point,
                        completed_rounds,
                        control["paused"],
                    ),
                )
                key = cv2.waitKey(1) & 0xFF
                if key == 27 or _debug_window_is_closed():
                    break
                time.sleep(0.08)
    finally:
        cv2.destroyAllWindows()
        print("自动运行已停止。")

if __name__ == "__main__":
    run_auto_player()
