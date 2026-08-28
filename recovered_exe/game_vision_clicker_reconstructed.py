"""Reconstructed source for the PyInstaller executable.

This file is a clean-room reconstruction based on:
- the executable's recovered module/function names,
- its embedded rules.json,
- its embedded template filenames,
- observed constants from bytecode disassembly.

It is intended to reproduce the same rule-driven screen automation architecture,
not to claim byte-for-byte equivalence with the original source.
"""

from __future__ import annotations

import ctypes
import json
import queue
import threading
import time
import tkinter as tk
from pathlib import Path

import cv2
import mss
import numpy as np


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "rules.json"
TEMPLATE_DIR = ROOT / "templates"

VK_ESCAPE = 27
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

MOUSE_MOVE_DURATION = 0.25

user32 = ctypes.windll.user32
user32.SetProcessDPIAware()


def key_pressed(vk: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def _virtual_screen() -> tuple[int, int, int, int]:
    return (
        user32.GetSystemMetrics(SM_XVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_YVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_CXVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_CYVIRTUALSCREEN),
    )


def move_mouse(x: int, y: int, duration: float = MOUSE_MOVE_DURATION) -> None:
    left, top, width, height = _virtual_screen()
    start = user32.GetCursorPos
    class Point(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    p = Point()
    start(ctypes.byref(p))
    x0, y0 = p.x, p.y

    steps = max(1, int(duration / 0.01))
    for i in range(1, steps + 1):
        t = i / steps
        xi = round(x0 + (x - x0) * t)
        yi = round(y0 + (y - y0) * t)
        nx = int((xi - left) * 65535 / max(1, width - 1))
        ny = int((yi - top) * 65535 / max(1, height - 1))
        user32.mouse_event(
            MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK,
            nx,
            ny,
            0,
            0,
        )
        time.sleep(duration / steps)


def foreground_is_game_like() -> bool:
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return False
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, len(buf))
    title = buf.value.strip().lower()
    # Keep this permissive: the recovered EXE used a foreground-window check.
    return bool(title)


def left_click(x: int, y: int) -> None:
    if not foreground_is_game_like():
        return
    move_mouse(x, y)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.05)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def load_rules() -> list[dict]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def crop_normalized(
    frame: np.ndarray,
    region: list[float],
) -> tuple[np.ndarray, tuple[int, int]]:
    h, w = frame.shape[:2]
    x1 = max(0, min(w, round(region[0] * w)))
    y1 = max(0, min(h, round(region[1] * h)))
    x2 = max(x1 + 1, min(w, round(region[2] * w)))
    y2 = max(y1 + 1, min(h, round(region[3] * h)))
    return frame[y1:y2, x1:x2], (x1, y1)


def match_rule(frame: np.ndarray, rule: dict) -> tuple[float, tuple[int, int]]:
    template_path = TEMPLATE_DIR / rule["template"]
    template = cv2.imread(str(template_path), cv2.IMREAD_COLOR)
    if template is None:
        return 0.0, (0, 0)

    search, offset = crop_normalized(frame, rule["detect_region"])
    if search.shape[0] < template.shape[0] or search.shape[1] < template.shape[1]:
        return 0.0, (0, 0)

    result = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(result)
    center = (
        offset[0] + loc[0] + template.shape[1] // 2,
        offset[1] + loc[1] + template.shape[0] // 2,
    )
    return float(score), center


def automation_worker(
    stop_event: threading.Event,
    paused_event: threading.Event,
    status_queue: queue.Queue,
) -> None:
    rules = sorted(load_rules(), key=lambda r: r.get("priority", 0), reverse=True)
    last_fired: dict[str, float] = {}

    with mss.mss() as sct:
        monitor = sct.monitors[1]

        while not stop_event.is_set():
            if key_pressed(VK_ESCAPE):
                stop_event.set()
                break

            if paused_event.is_set():
                status_queue.put(("paused", None))
                time.sleep(0.1)
                continue

            shot = np.asarray(sct.grab(monitor))
            frame = cv2.cvtColor(shot, cv2.COLOR_BGRA2BGR)
            fh, fw = frame.shape[:2]

            fired = False
            best_name = "等待匹配"
            best_score = 0.0

            for rule in rules:
                score, _ = match_rule(frame, rule)
                if score > best_score:
                    best_score = score
                    best_name = rule["name"]

                threshold = float(rule.get("threshold", 0.82))
                now = time.monotonic()
                cooldown = float(rule.get("rearm_after", 1.5))
                previous = last_fired.get(rule["name"], -1e9)

                if score < threshold or now - previous < cooldown:
                    continue

                px = int(rule["click_point"][0] * fw) + int(monitor["left"])
                py = int(rule["click_point"][1] * fh) + int(monitor["top"])
                left_click(px, py)

                if "followup_click_point" in rule:
                    time.sleep(float(rule.get("followup_delay", 0.35)))
                    fx = int(rule["followup_click_point"][0] * fw) + int(monitor["left"])
                    fy = int(rule["followup_click_point"][1] * fh) + int(monitor["top"])
                    left_click(fx, fy)

                last_fired[rule["name"]] = time.monotonic()
                status_queue.put(("fired", (rule["name"], score)))
                fired = True
                break

            if not fired:
                status_queue.put(("scan", (best_name, best_score)))

            time.sleep(0.08)


class ControlPanel:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("逆水寒大乱斗助手 - Reconstructed")
        self.root.geometry("520x260")

        self.stop_event = threading.Event()
        self.paused_event = threading.Event()
        self.status_queue: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None

        self.status_var = tk.StringVar(value="未启动")

        tk.Label(
            self.root,
            text="逆水寒大乱斗助手",
            font=("Microsoft YaHei UI", 18, "bold"),
        ).pack(pady=(18, 8))

        tk.Label(
            self.root,
            textvariable=self.status_var,
            font=("Microsoft YaHei UI", 11),
            wraplength=470,
        ).pack(pady=8)

        row = tk.Frame(self.root)
        row.pack(pady=14)

        tk.Button(row, text="启动", width=12, command=self.start).pack(side="left", padx=6)
        tk.Button(row, text="暂停/继续", width=12, command=self.toggle_pause).pack(side="left", padx=6)
        tk.Button(row, text="停止", width=12, command=self.stop).pack(side="left", padx=6)

        tk.Label(
            self.root,
            text="Esc 也可停止。模板和规则来自 EXE 内嵌资源。",
            font=("Microsoft YaHei UI", 9),
        ).pack(pady=6)

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(100, self.poll_status)

    def start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        self.stop_event.clear()
        self.paused_event.clear()
        self.worker = threading.Thread(
            target=automation_worker,
            args=(self.stop_event, self.paused_event, self.status_queue),
            daemon=True,
        )
        self.worker.start()
        self.status_var.set("运行中")

    def toggle_pause(self) -> None:
        if self.paused_event.is_set():
            self.paused_event.clear()
            self.status_var.set("运行中")
        else:
            self.paused_event.set()
            self.status_var.set("已暂停")

    def stop(self) -> None:
        self.stop_event.set()
        self.status_var.set("已停止")

    def poll_status(self) -> None:
        try:
            while True:
                kind, payload = self.status_queue.get_nowait()
                if kind == "scan" and payload:
                    name, score = payload
                    self.status_var.set(f"扫描中：{name} / {score:.3f}")
                elif kind == "fired" and payload:
                    name, score = payload
                    self.status_var.set(f"已执行：{name} / {score:.3f}")
                elif kind == "paused":
                    self.status_var.set("已暂停")
        except queue.Empty:
            pass

        if not self.stop_event.is_set() or (self.worker and self.worker.is_alive()):
            self.root.after(100, self.poll_status)
        else:
            self.root.after(250, self.poll_status)

    def close(self) -> None:
        self.stop_event.set()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    ControlPanel().run()
