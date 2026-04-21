import math
import queue
import subprocess
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk

import yaml
from PIL import Image, ImageDraw, ImageTk


@dataclass
class DebugConfig:
    image_path: str = "./image/image_monitor.png"
    max_slot: int = 12
    area_scope: int = 50
    area_point_num: int = 8
    abs_monitor_size: list[int] = None
    abs_input_size: list[int] = None
    landscape_mode: bool = False
    landscape_rotation: str = "right"
    reverse_monitor: bool = False
    specified_devices: str = ""
    exp_image_dict: dict[str, str] = None


DEFAULT_EXP_IMAGE_DICT = {
    "41-65-93": "A1",
    "87-152-13": "A2",
    "213-109-81": "A3",
    "23-222-55": "A4",
    "69-203-71": "A5",
    "147-253-55": "A6",
    "77-19-35": "A7",
    "159-109-79": "A8",
    "87-217-111": "B1",
    "149-95-154": "B2",
    "97-233-9": "B3",
    "159-27-222": "B4",
    "152-173-186": "B5",
    "192-185-149": "B6",
    "158-45-23": "B7",
    "197-158-219": "B8",
    "127-144-79": "C1",
    "242-41-155": "C2",
    "69-67-213": "D1",
    "105-25-130": "D2",
    "17-39-170": "D3",
    "97-103-203": "D4",
    "113-25-77": "D5",
    "21-21-140": "D6",
    "155-179-166": "D7",
    "55-181-134": "D8",
    "61-33-27": "E1",
    "51-91-95": "E2",
    "143-227-63": "E3",
    "216-67-226": "E4",
    "202-181-245": "E5",
    "99-11-183": "E6",
    "75-119-224": "E7",
    "182-19-85": "E8",
}


def load_config(yaml_path: str) -> DebugConfig:
    config = DebugConfig()
    config.abs_monitor_size = [1600, 2560]
    config.abs_input_size = [1600, 2560]
    config.exp_image_dict = dict(DEFAULT_EXP_IMAGE_DICT)

    try:
        with open(yaml_path, "r", encoding="utf-8") as file:
            raw = yaml.safe_load(file) or {}
    except FileNotFoundError:
        return config

    config.image_path = raw.get("IMAGE_PATH", config.image_path)
    config.max_slot = raw.get("MAX_SLOT", config.max_slot)
    config.area_scope = raw.get("AREA_SCOPE", config.area_scope)
    config.area_point_num = raw.get("AREA_POINT_NUM", config.area_point_num)
    config.abs_monitor_size = raw.get("ANDROID_ABS_MONITOR_SIZE", config.abs_monitor_size)
    config.abs_input_size = raw.get("ANDROID_ABS_INPUT_SIZE", config.abs_input_size)
    config.landscape_mode = raw.get("ANDROID_LANDSCAPE_MODE", config.landscape_mode)
    config.landscape_rotation = raw.get("ANDROID_LANDSCAPE_ROTATION", config.landscape_rotation)
    config.reverse_monitor = raw.get("ANDROID_REVERSE_MONITOR", config.reverse_monitor)
    config.specified_devices = raw.get("SPECIFIED_DEVICES", config.specified_devices)
    config.exp_image_dict = raw.get("exp_image_dict", config.exp_image_dict)
    return config


def get_color_name(pixel: tuple[int, int, int]) -> str:
    return f"{pixel[0]}-{pixel[1]}-{pixel[2]}"


def get_colors_in_area(
    image: Image.Image,
    x: int,
    y: int,
    area_scope: int,
    area_point_num: int,
) -> list[str]:
    width, height = image.size
    colors = set()
    angle_increment = 360.0 / area_point_num
    cos_values = [math.cos(math.radians(i * angle_increment)) for i in range(area_point_num)]
    sin_values = [math.sin(math.radians(i * angle_increment)) for i in range(area_point_num)]

    if 0 <= x < width and 0 <= y < height:
        colors.add(get_color_name(image.getpixel((x, y))))

    for i in range(area_point_num):
        dx = int(area_scope * cos_values[i])
        dy = int(area_scope * sin_values[i])
        px = x + dx
        py = y + dy
        if 0 <= px < width and 0 <= py < height:
            colors.add(get_color_name(image.getpixel((px, py))))

    return list(colors)


class TouchEventReader(threading.Thread):
    def __init__(self, cfg: DebugConfig, out_queue: queue.Queue):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.out_queue = out_queue
        self.stop_event = threading.Event()
        self.process = None
        self.touch_data = [{"p": False, "x": 0, "y": 0} for _ in range(cfg.max_slot)]
        self.raw_x = [0 for _ in range(cfg.max_slot)]
        self.raw_y = [0 for _ in range(cfg.max_slot)]
        self.touch_index = 0
        if cfg.landscape_mode:
            self.abs_multi_x = cfg.abs_monitor_size[1] / cfg.abs_input_size[0]
            self.abs_multi_y = cfg.abs_monitor_size[0] / cfg.abs_input_size[1]
        else:
            self.abs_multi_x = cfg.abs_monitor_size[0] / cfg.abs_input_size[0]
            self.abs_multi_y = cfg.abs_monitor_size[1] / cfg.abs_input_size[1]

    def _map_touch_position(self, raw_x: int, raw_y: int) -> tuple[int, int]:
        scaled_x = raw_x * self.abs_multi_x
        scaled_y = raw_y * self.abs_multi_y

        if self.cfg.landscape_mode:
            if self.cfg.landscape_rotation == "left":
                mapped_x = scaled_y
                mapped_y = self.cfg.abs_monitor_size[1] - scaled_x
            else:
                mapped_x = self.cfg.abs_monitor_size[0] - scaled_y
                mapped_y = scaled_x
        else:
            mapped_x = scaled_x
            mapped_y = scaled_y

        if self.cfg.reverse_monitor:
            mapped_x = self.cfg.abs_monitor_size[0] - mapped_x
            mapped_y = self.cfg.abs_monitor_size[1] - mapped_y

        x = int(max(0, min(self.cfg.abs_monitor_size[0] - 1, mapped_x)))
        y = int(max(0, min(self.cfg.abs_monitor_size[1] - 1, mapped_y)))
        return x, y

    def run(self):
        adb_cmd = "adb shell getevent -l"
        if self.cfg.specified_devices:
            adb_cmd = f"adb -s {self.cfg.specified_devices} shell getevent -l"

        self.process = subprocess.Popen(
            adb_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

        key_is_changed = False
        for raw_line in iter(self.process.stdout.readline, b""):
            if self.stop_event.is_set():
                break

            line = raw_line.decode("utf-8", errors="ignore").strip()
            parts = line.split()
            if len(parts) < 4:
                continue

            event_type = parts[2]
            event_value_hex = parts[3]

            try:
                event_value = int(event_value_hex, 16)
            except ValueError:
                continue

            if event_type == "ABS_MT_POSITION_X":
                key_is_changed = True
                self.raw_x[self.touch_index] = event_value
                x, y = self._map_touch_position(self.raw_x[self.touch_index], self.raw_y[self.touch_index])
                self.touch_data[self.touch_index]["x"] = x
                self.touch_data[self.touch_index]["y"] = y
            elif event_type == "ABS_MT_POSITION_Y":
                key_is_changed = True
                self.raw_y[self.touch_index] = event_value
                x, y = self._map_touch_position(self.raw_x[self.touch_index], self.raw_y[self.touch_index])
                self.touch_data[self.touch_index]["x"] = x
                self.touch_data[self.touch_index]["y"] = y
            elif event_type == "ABS_MT_SLOT":
                key_is_changed = True
                self.touch_index = max(0, min(event_value, self.cfg.max_slot - 1))
            elif event_type == "ABS_MT_TRACKING_ID":
                key_is_changed = True
                self.touch_data[self.touch_index]["p"] = event_value_hex != "ffffffff"
            elif event_type == "SYN_REPORT" and key_is_changed:
                snapshot = {
                    "touch_data": [dict(slot) for slot in self.touch_data],
                    "timestamp": time.time(),
                }
                self.out_queue.put(snapshot)
                key_is_changed = False

        self._terminate_process()

    def stop(self):
        self.stop_event.set()
        self._terminate_process()

    def _terminate_process(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.process.kill()


class TouchDebugApp:
    def __init__(self, cfg: DebugConfig):
        self.cfg = cfg
        self.root = tk.Tk()
        self.root.title("Maimai Touch Debug Visualizer")
        self.root.geometry("1300x840")

        self.raw_image = Image.open(cfg.image_path).convert("RGB")
        self.image_for_sampling = self.raw_image.copy()

        self.image_scale = min(900 / self.raw_image.size[0], 800 / self.raw_image.size[1], 1.0)
        self.display_size = (
            int(self.raw_image.size[0] * self.image_scale),
            int(self.raw_image.size[1] * self.image_scale),
        )

        self.base_display_image = self.raw_image.resize(self.display_size, Image.Resampling.NEAREST)
        self.tk_image = ImageTk.PhotoImage(self.base_display_image)

        self.queue = queue.Queue()
        self.reader = TouchEventReader(cfg, self.queue)
        self.last_event_time = 0.0
        self.active_keys = []

        self._build_layout()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_layout(self):
        main_frame = ttk.Frame(self.root, padding=8)
        main_frame.pack(fill="both", expand=True)

        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side="left", fill="both", expand=True)

        self.canvas = tk.Canvas(
            left_frame,
            width=self.display_size[0],
            height=self.display_size[1],
            background="#111111",
            highlightthickness=0,
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas_image = self.canvas.create_image(0, 0, anchor="nw", image=self.tk_image)

        right_frame = ttk.Frame(main_frame, width=320)
        right_frame.pack(side="right", fill="y", padx=(10, 0))
        right_frame.pack_propagate(False)

        self.status_var = tk.StringVar(value="Waiting for touch data...")
        ttk.Label(right_frame, textvariable=self.status_var, wraplength=300).pack(anchor="w", pady=(0, 8))

        ttk.Label(right_frame, text="Active keys").pack(anchor="w")
        self.keys_var = tk.StringVar(value="-")
        ttk.Label(
            right_frame,
            textvariable=self.keys_var,
            font=("Consolas", 12, "bold"),
            foreground="#0a7f2e",
            wraplength=300,
            justify="left",
        ).pack(anchor="w", pady=(2, 10))

        ttk.Label(right_frame, text="Touch slots").pack(anchor="w")
        self.slots_text = tk.Text(right_frame, height=28, width=40, font=("Consolas", 10))
        self.slots_text.pack(fill="both", expand=True)
        self.slots_text.configure(state="disabled")

        ttk.Label(
            right_frame,
            text="Tip: run this window while touching the screen to verify mapping and coordinate scaling.",
            wraplength=300,
        ).pack(anchor="w", pady=(10, 0))

    def _draw_touch_overlay(self, touch_data: list[dict]):
        frame = self.base_display_image.copy()
        draw = ImageDraw.Draw(frame)

        for index, point in enumerate(touch_data):
            if not point["p"]:
                continue
            x = point["x"] * self.image_scale
            y = point["y"] * self.image_scale
            radius = max(6, int(self.cfg.area_scope * self.image_scale))
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline="#ff4444", width=2)
            draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill="#00d6ff", outline="#00d6ff")
            draw.text((x + 8, y + 8), f"S{index}", fill="#ffffff")

        self.tk_image = ImageTk.PhotoImage(frame)
        self.canvas.itemconfig(self.canvas_image, image=self.tk_image)

    def _detect_keys(self, touch_data: list[dict]) -> list[str]:
        keys = set()
        for point in touch_data:
            if not point["p"]:
                continue
            rgb_values = get_colors_in_area(
                self.image_for_sampling,
                point["x"],
                point["y"],
                self.cfg.area_scope,
                self.cfg.area_point_num,
            )
            for rgb in rgb_values:
                if rgb in self.cfg.exp_image_dict:
                    keys.add(self.cfg.exp_image_dict[rgb])
        return sorted(keys)

    def _render_slot_text(self, touch_data: list[dict]):
        lines = []
        for index, point in enumerate(touch_data):
            state = "DOWN" if point["p"] else "UP  "
            lines.append(f"slot {index:02d}  {state}   x={point['x']:4d}  y={point['y']:4d}")
        content = "\n".join(lines)

        self.slots_text.configure(state="normal")
        self.slots_text.delete("1.0", tk.END)
        self.slots_text.insert("1.0", content)
        self.slots_text.configure(state="disabled")

    def _tick(self):
        latest = None
        while not self.queue.empty():
            latest = self.queue.get()

        if latest is not None:
            touch_data = latest["touch_data"]
            self.last_event_time = latest["timestamp"]
            self.active_keys = self._detect_keys(touch_data)
            self._draw_touch_overlay(touch_data)
            self._render_slot_text(touch_data)
            self.keys_var.set(", ".join(self.active_keys) if self.active_keys else "-")

        if self.last_event_time <= 0:
            self.status_var.set("Waiting for touch data...")
        else:
            elapsed = time.time() - self.last_event_time
            self.status_var.set(f"Last event: {elapsed:.2f}s ago")

        self.root.after(33, self._tick)

    def run(self):
        self.reader.start()
        self._tick()
        self.root.mainloop()

    def _on_close(self):
        self.reader.stop()
        self.root.destroy()


def main():
    cfg = load_config("config.yaml")
    app = TouchDebugApp(cfg)
    app.run()


if __name__ == "__main__":
    main()
