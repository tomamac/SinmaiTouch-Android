from PIL import Image
import subprocess
import copy
import time
import threading
import queue
import serial
import math
import yaml
import os
import sys

# Default configuration used when no config file is found
# Path to the prepared image
IMAGE_PATH = "./image/image_monitor.png"
# Serial port
COM_PORT = "COM33"
# Baud rate
COM_BAUDRATE = 9600
# Number of Android multitouch slots
MAX_SLOT = 12
# Detection area radius in pixels
AREA_SCOPE = 50
# Number of sample points on the detection circle
AREA_POINT_NUM = 8
# Actual Android screen size (pixels)
ANDROID_ABS_MONITOR_SIZE = [1600, 2560]
# Android touch input size (pixels)
ANDROID_ABS_INPUT_SIZE = [1600, 2560]
# Enable landscape coordinate transform
ANDROID_LANDSCAPE_MODE = False
# Landscape rotation direction: "right" (clockwise) or "left" (counterclockwise)
ANDROID_LANDSCAPE_ROTATION = "right"
# Enable screen inversion (use when the charging port faces up)
ANDROID_REVERSE_MONITOR = False
# Whether touch_thread uses sleep. Off by default; enable if CPU usage is high, disable if swipe latency gets large.
TOUCH_THREAD_SLEEP_MODE = False
# Delay per sleep cycle in microseconds (default: 100)
TOUCH_THREAD_SLEEP_DELAY = 100
# Time compensation value; calibrate for your own PC performance
TIME_COMPENSATION = 1.0
# If you need a specific touch device, set its serial from "adb devices"; leave empty for single-device mode only.
SPECIFIED_DEVICES = ""

exp_list = [
    ["A1", "A2", "A3", "A4", "A5", ],
    ["A6", "A7", "A8", "B1", "B2", ],
    ["B3", "B4", "B5", "B6", "B7", ],
    ["B8", "C1", "C2", "D1", "D2", ],
    ["D3", "D4", "D5", "D6", "D7", ],
    ["D8", "E1", "E2", "E3", "E4", ],
    ["E5", "E6", "E7", "E8", ],
]
exp_image_dict = {'41-65-93': 'A1', '87-152-13': 'A2', '213-109-81': 'A3', '23-222-55': 'A4', '69-203-71': 'A5',
                  '147-253-55': 'A6', '77-19-35': 'A7', '159-109-79': 'A8', '87-217-111': 'B1', '149-95-154': 'B2',
                  '97-233-9': 'B3', '159-27-222': 'B4', '152-173-186': 'B5', '192-185-149': 'B6', '158-45-23': 'B7',
                  '197-158-219': 'B8', '127-144-79': 'C1', '242-41-155': 'C2', '69-67-213': 'D1', '105-25-130': 'D2',
                  '17-39-170': 'D3', '97-103-203': 'D4', '113-25-77': 'D5', '21-21-140': 'D6', '155-179-166': 'D7',
                  '55-181-134': 'D8', '61-33-27': 'E1', '51-91-95': 'E2', '143-227-63': 'E3', '216-67-226': 'E4',
                  '202-181-245': 'E5', '99-11-183': 'E6', '75-119-224': 'E7', '182-19-85': 'E8'}


class SerialManager:


    def __init__(self):
        self.p1Serial = serial.Serial(COM_PORT, COM_BAUDRATE)
        self.settingPacket = bytearray([40, 0, 0, 0, 0, 41])
        self.startUp = False
        self.recvData = ""
        self.exit_flag = False

        self.touchQueue = queue.Queue()
        self.data_lock = threading.Lock()
        self.touchThread = threading.Thread(target=self.touch_thread, daemon=True)
        self.writeThread = threading.Thread(target=self.write_thread, daemon=True)
        self.now_touch_data = b''
        self.now_touch_keys = []
        self.ping_touch_thread()

    def start(self):
        print(f"开始监听 {COM_PORT} 串口...")
        self.touchThread.start()
        self.writeThread.start()

    def ping_touch_thread(self):
        self.touchQueue.put([self.build_touch_package(exp_list), []])

    def touch_thread(self):
        while not self.exit_flag:
            # start_time = time.perf_counter()
            if self.p1Serial.is_open:
                self.read_data(self.p1Serial)
            if not self.touchQueue.empty():
                # print("touchQueue is not empty, processing now")
                s_temp = self.touchQueue.get()
                self.update_touch(s_temp)
            # Delay to prevent excessive CPU usage
            if TOUCH_THREAD_SLEEP_MODE:
                microsecond_sleep(TOUCH_THREAD_SLEEP_DELAY)
            # print("Execution time per loop:", (time.perf_counter() - start_time) * 1e3, "ms")

    def write_thread(self):
        while not self.exit_flag:
            # # Delay tuned for baud rate
            # time.sleep(0.0075)  # 9600
            # # time.sleep(0.002)  # 115200
            time.sleep(0.000001)  # Avoid excessive latency
            if not self.startUp:
                # print("Not started yet")
                continue
            # print(self.now_touch_data)
            with self.data_lock:
                self.send_touch(self.p1Serial, self.now_touch_data)

    def stop(self):
        print("正在停止...")
        self.exit_flag = True
        time.sleep(0.1)  # Give threads time to exit
        if self.p1Serial.is_open:
            self.p1Serial.close()
        print("已停止")

    def read_data(self, ser):
        if ser.in_waiting == 6:
            self.recvData = ser.read(6).decode()
            # print(self.recvData)
            self.touch_setup(ser, self.recvData)

    def touch_setup(self, ser, data):
        byte_data = ord(data[3])
        if byte_data in [76, 69]:
            self.startUp = False
        elif byte_data in [114, 107]:
            for i in range(1, 5):
                self.settingPacket[i] = ord(data[i])
            ser.write(self.settingPacket)
        elif byte_data == 65:
            self.startUp = True
            print("已连接到游戏")

    def send_touch(self, ser, data):
        ser.write(data)

    # def build_touch_package(self, sl):
    #     sum_list = [0, 0, 0, 0, 0, 0, 0]
    #     for i in range(len(sl)):
    #         for j in range(len(sl[i])):
    #             if sl[i][j] == 1:
    #                 sum_list[i] += (2 ** j)
    #     s = "28 "
    #     for i in sum_list:
    #         s += hex(i)[2:].zfill(2).upper() + " "
    #     s += "29"
    #     # print(s)
    #     return bytes.fromhex(s)

    def build_touch_package(self, sl):
        sum_list = [sum(2 ** j for j, val in enumerate(row) if val == 1) for row in sl]
        hex_list = [hex(i)[2:].zfill(2).upper() for i in sum_list]
        s = "28 " + " ".join(hex_list) + " 29"
        # print(s)
        return bytes.fromhex(s)

    def update_touch(self, s_temp):
        # if not self.startUp:
        #     print("Not started yet")
        #     return
        with self.data_lock:
            self.now_touch_data = s_temp[0]
            self.send_touch(self.p1Serial, s_temp[0])
            self.now_touch_keys = s_temp[1]
        print("Touch Keys:", s_temp[1])
        # else:
        #     self.send_touch(self.p2Serial, s_temp[0])

    def change_touch(self, sl, touch_keys):
        self.touchQueue.put([self.build_touch_package(sl), touch_keys])


def restart_script():
    print("正在重启...")
    serial_manager.stop()
    sys.exit(42)


def microsecond_sleep(sleep_time):
    end_time = time.perf_counter() + (sleep_time - TIME_COMPENSATION) / 1e6  # Time compensation; calibrate for your PC.
    while time.perf_counter() < end_time:
        pass


# Sample 9 points in a circular area for detection
def get_colors_in_area(x, y):
    colors = set()  # Use a set to avoid duplicate color values
    num_points = AREA_POINT_NUM  # Number of points to sample
    angle_increment = 360.0 / num_points  # Angle increment
    cos_values = [math.cos(math.radians(i * angle_increment)) for i in range(num_points)]
    sin_values = [math.sin(math.radians(i * angle_increment)) for i in range(num_points)]
    # Process center point
    if 0 <= x < exp_image_width and 0 <= y < exp_image_height:
        colors.add(get_color_name(exp_image.getpixel((x, y))))
    # Process points on the circle
    for i in range(num_points):
        dx = int(AREA_SCOPE * cos_values[i])
        dy = int(AREA_SCOPE * sin_values[i])
        px = x + dx
        py = y + dy
        if 0 <= px < exp_image_width and 0 <= py < exp_image_height:
            colors.add(get_color_name(exp_image.getpixel((px, py))))
    return list(colors)


def get_color_name(pixel):
    return str(pixel[0]) + "-" + str(pixel[1]) + "-" + str(pixel[2])


def map_touch_position(raw_x, raw_y):
    scaled_x = raw_x * abs_multi_x
    scaled_y = raw_y * abs_multi_y

    if ANDROID_LANDSCAPE_MODE:
        if ANDROID_LANDSCAPE_ROTATION == "left":
            mapped_x = scaled_y
            mapped_y = ANDROID_ABS_MONITOR_SIZE[1] - scaled_x
        else:
            mapped_x = ANDROID_ABS_MONITOR_SIZE[0] - scaled_y
            mapped_y = scaled_x
    else:
        mapped_x = scaled_x
        mapped_y = scaled_y

    if ANDROID_REVERSE_MONITOR:
        mapped_x = ANDROID_ABS_MONITOR_SIZE[0] - mapped_x
        mapped_y = ANDROID_ABS_MONITOR_SIZE[1] - mapped_y

    x = int(max(0, min(ANDROID_ABS_MONITOR_SIZE[0] - 1, mapped_x)))
    y = int(max(0, min(ANDROID_ABS_MONITOR_SIZE[1] - 1, mapped_y)))
    return x, y


def convert(touch_data):
    copy_exp_list = copy.deepcopy(exp_list)
    touch_keys = {exp_image_dict[rgb_str] for i in touch_data if i["p"] for rgb_str in
                  get_colors_in_area(i["x"], i["y"]) if
                  rgb_str in exp_image_dict}
    # print("Touch Keys:", touch_keys)
    # touched = sum(1 for i in touch_data if i["p"])
    # print("Touched:", touched)
    touch_keys_list = list(touch_keys)
    copy_exp_list = [[1 if item in touch_keys_list else 0 for item in sublist] for sublist in copy_exp_list]
    # print(copy_exp_list)
    serial_manager.change_touch(copy_exp_list, touch_keys_list)


# def convert(touch_data):
#     copy_exp_list = copy.deepcopy(exp_list)
#     touch_keys = set()
#     touched = 0
#     for i in touch_data:
#         if not i["p"]:
#             continue
#         touched += 1
#         x = i["x"]
#         y = i["y"]
#         for rgb_str in get_colors_in_area(x, y):
#             if not rgb_str in exp_image_dict:
#                 continue
#             touch_keys.add(exp_image_dict[rgb_str])
#     # print("Touched:", touched)
#     # print("Touch Keys:", touch_keys)
#     touch_keys_list = list(touch_keys)
#     for i in range(len(copy_exp_list)):
#         for j in range(len(copy_exp_list[i])):
#             if copy_exp_list[i][j] in touch_keys_list:
#                 copy_exp_list[i][j] = 1
#             else:
#                 copy_exp_list[i][j] = 0
#     # print(copy_exp_list)
#     serial_manager.change_touch(copy_exp_list, touch_keys_list)


def getevent():
    # List storing multitouch data
    touch_data = [{"p": False, "x": 0, "y": 0} for _ in range(MAX_SLOT)]
    # Current number of pressed touch points
    touch_sum = 0
    # Currently selected SLOT index
    touch_index = 0

    # Run adb shell getevent and capture output
    adb_cmd = 'adb shell getevent -l'
    if SPECIFIED_DEVICES:
        adb_cmd = 'adb -s ' + SPECIFIED_DEVICES + ' shell getevent -l'
    process = subprocess.Popen(adb_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    key_is_changed = False
    raw_x = [0 for _ in range(MAX_SLOT)]
    raw_y = [0 for _ in range(MAX_SLOT)]

    # Read realtime output
    for line in iter(process.stdout.readline, b''):
        try:

            event = line.decode('utf-8').strip()
            parts = event.split()

            # Skip irrelevant lines
            if len(parts) < 4:
                continue

            event_type = parts[2]
            event_value_hex = parts[3]
            event_value = int(event_value_hex, 16)

            if event_type == 'ABS_MT_POSITION_X':
                key_is_changed = True
                raw_x[touch_index] = event_value
                x, y = map_touch_position(raw_x[touch_index], raw_y[touch_index])
                touch_data[touch_index]["x"] = x
                touch_data[touch_index]["y"] = y

            elif event_type == 'ABS_MT_POSITION_Y':
                key_is_changed = True
                raw_y[touch_index] = event_value
                x, y = map_touch_position(raw_x[touch_index], raw_y[touch_index])
                touch_data[touch_index]["x"] = x
                touch_data[touch_index]["y"] = y

            elif event_type == 'SYN_REPORT':
                if key_is_changed:
                    convert(touch_data)
                    key_is_changed = False

            elif event_type == 'ABS_MT_SLOT':
                key_is_changed = True
                touch_index = event_value
                if touch_index >= touch_sum:
                    touch_sum = touch_index + 1

            elif event_type == 'ABS_MT_TRACKING_ID':
                key_is_changed = True
                if event_value_hex == "ffffffff":
                    touch_data[touch_index]['p'] = False
                    touch_sum = max(0, touch_sum - 1)
                else:
                    touch_data[touch_index]['p'] = True
                    touch_sum += 1

        except Exception as e:
            event_error_output = line.decode('utf-8')
            if "name" not in event_error_output:
                continue
            print(event_error_output)


if __name__ == "__main__":
    yaml_file_path = 'config.yaml'
    if len(sys.argv) > 1:
        yaml_file_path = sys.argv[1]
    if os.path.isfile(yaml_file_path):
        print("使用配置文件:", yaml_file_path)
        with open(yaml_file_path, 'r', encoding='utf-8') as file:
            c = yaml.safe_load(file)
        IMAGE_PATH = c["IMAGE_PATH"]
        COM_PORT = c["COM_PORT"]
        COM_BAUDRATE = c["COM_BAUDRATE"]
        MAX_SLOT = c["MAX_SLOT"]
        AREA_SCOPE = c["AREA_SCOPE"]
        AREA_POINT_NUM = c["AREA_POINT_NUM"]
        ANDROID_ABS_MONITOR_SIZE = c["ANDROID_ABS_MONITOR_SIZE"]
        ANDROID_ABS_INPUT_SIZE = c["ANDROID_ABS_INPUT_SIZE"]
        ANDROID_LANDSCAPE_MODE = c.get("ANDROID_LANDSCAPE_MODE", ANDROID_LANDSCAPE_MODE)
        ANDROID_LANDSCAPE_ROTATION = c.get("ANDROID_LANDSCAPE_ROTATION", ANDROID_LANDSCAPE_ROTATION)
        ANDROID_REVERSE_MONITOR = c["ANDROID_REVERSE_MONITOR"]
        TOUCH_THREAD_SLEEP_MODE = c["TOUCH_THREAD_SLEEP_MODE"]
        TOUCH_THREAD_SLEEP_DELAY = c["TOUCH_THREAD_SLEEP_DELAY"]
        TIME_COMPENSATION = c["TIME_COMPENSATION"]
        SPECIFIED_DEVICES = c["SPECIFIED_DEVICES"]
        exp_image_dict = c["exp_image_dict"]
    else:
        print("未找到配置文件, 使用默认配置")

    exp_image = Image.open(IMAGE_PATH)
    exp_image_width, exp_image_height = exp_image.size
    if ANDROID_LANDSCAPE_MODE:
        abs_multi_x = ANDROID_ABS_MONITOR_SIZE[1] / ANDROID_ABS_INPUT_SIZE[0]
        abs_multi_y = ANDROID_ABS_MONITOR_SIZE[0] / ANDROID_ABS_INPUT_SIZE[1]
    else:
        abs_multi_x = ANDROID_ABS_MONITOR_SIZE[0] / ANDROID_ABS_INPUT_SIZE[0]
        abs_multi_y = ANDROID_ABS_MONITOR_SIZE[1] / ANDROID_ABS_INPUT_SIZE[1]
    print("当前触控区域X轴放大倍数:", abs_multi_x)
    print("当前触控区域Y轴放大倍数:", abs_multi_y)
    print("当前链接到端口：", COM_PORT)
    print("当前方向模式:", "横屏" if ANDROID_LANDSCAPE_MODE else "竖屏")
    if ANDROID_LANDSCAPE_MODE:
        print("横屏旋转方向:", ANDROID_LANDSCAPE_ROTATION)
    print(('已' if ANDROID_REVERSE_MONITOR else '未') + "开启屏幕反转")
    serial_manager = SerialManager()
    serial_manager.start()
    getevent_thread = threading.Thread(target=getevent, daemon=True)
    getevent_thread.start()

    try:
        while True:
            input_str = input().strip()
            if len(input_str) == 0:
                continue
            if input_str == 'help':
                print("可用命令:")
                print("start   - 手动连接到游戏")
                print("reverse - 切换屏幕反转")
                print("restart - 重启脚本")
                print("exit    - 退出脚本")
                print("help    - 显示此帮助信息")
            elif input_str == 'start':
                serial_manager.startUp = True
                print("已连接到游戏")
            elif input_str == 'reverse':
                ANDROID_REVERSE_MONITOR = not ANDROID_REVERSE_MONITOR
                print("已" + ('开启' if ANDROID_REVERSE_MONITOR else '关闭') + "屏幕反转")
            elif input_str == 'restart':
                restart_script()
            elif input_str == 'exit':
                print("正在退出")
                serial_manager.stop()
                sys.exit(0)
            else:
                print("未知的命令，输入 'help' 查看可用命令")
    except KeyboardInterrupt:
        print("\n检测到中断信号")
        serial_manager.stop()
        sys.exit(0)
