"""Desk companion display app.

240x240 ST7789 LCD: persistent pet cultivation, growth and environment.
128x64 SSD1306 OLED: Beijing time and PIR + VL53L0X fused study state.
"""

import dht
import framebuf
import time
from machine import ADC, Pin, SoftI2C, SPI
from fusion_tracker import DistanceMedianFilter, FusionPresenceTracker
from pet_growth import PetGrowthSystem
from st7789 import ST7789
from vl53l0x import VL53L0X


# Keep a short UART recovery window before GPIO43/GPIO44 become LCD DC/CS.
time.sleep(3)


class SSD1306(framebuf.FrameBuffer):
    def __init__(self, i2c, width=128, height=64, address=0x3C):
        self.i2c = i2c
        self.width = width
        self.height = height
        self.address = address
        self.pages = height // 8
        self.buffer = bytearray(self.pages * width)
        super().__init__(self.buffer, width, height, framebuf.MONO_VLSB)
        for command in (
            0xAE, 0x20, 0x00, 0x40, 0xA1, 0xA8, height - 1, 0xC8,
            0xD3, 0x00, 0xDA, 0x12, 0xD5, 0x80, 0xD9, 0xF1, 0xDB,
            0x30, 0x81, 0xFF, 0xA4, 0xA6, 0x8D, 0x14, 0xAF,
        ):
            self._command(command)
        self.fill(0)
        self.show()

    def _command(self, command):
        self.i2c.writeto(self.address, bytes((0x80, command)))

    def show(self):
        for command, value in ((0x21, self.width - 1), (0x22, self.pages - 1)):
            self._command(command)
            self._command(0)
            self._command(value)
        self.i2c.writeto(self.address, b"\x40" + self.buffer)


def scaled_text(target, text, x, y, scale, color):
    """Draw MicroPython's built-in 8x8 font at an integer scale."""
    width = len(text) * 8
    mono = framebuf.FrameBuffer(bytearray(width), width, 8, framebuf.MONO_HLSB)
    mono.fill(0)
    mono.text(text, 0, 0, 1)
    for px in range(width):
        for py in range(8):
            if mono.pixel(px, py):
                target.fill_rect(x + px * scale, y + py * scale, scale, scale, color)


def load_binary(path):
    try:
        with open(path, "rb") as binary_file:
            return binary_file.read()
    except Exception:
        return None


def draw_lcd_static(target, black, white):
    """Build the fixed LCD layout; pet sprites are copied in separately."""
    target.fill(black)

    # Left: animation area and space for study/goal/event text.
    target.hline(7, 27, 136, white)

    # Right: stamina, growth, today's study and environment quality.
    target.rect(153, 4, 83, 232, white)
    target.text("STATS", 174, 10, white)
    target.text("HP", 164, 30, white)
    target.rect(164, 44, 60, 10, white)
    target.text("GROW", 164, 62, white)
    target.rect(164, 76, 60, 10, white)
    target.text("TODAY", 174, 96, white)
    target.hline(164, 126, 60, white)
    target.hline(164, 184, 60, white)


def blit_pet_sprite(target_buffer, sprite, x=7, y=36, width=136, height=112):
    """Copy a pre-rendered high-byte-first RGB565 sprite into the LCD buffer."""
    row_bytes = width * 2
    if sprite is None or len(sprite) != row_bytes * height:
        return False
    for row in range(height):
        source = row * row_bytes
        destination = ((y + row) * 240 + x) * 2
        target_buffer[destination : destination + row_bytes] = sprite[
            source : source + row_bytes
        ]
    return True


def read_adc12(adc):
    try:
        return adc.read_u16() >> 4
    except AttributeError:
        return adc.read()


def save_state(
    v1, v2, pir_value, present, study_seconds, internal_state,
    distance_mm, raw_distance_mm, tof_healthy, lcd_ok, beijing_time,
    pet_state,
):
    try:
        with open("/state.txt", "w") as state_file:
            state_file.write(
                "v1=%d v2=%d diff=%d pir=%d present=%d "
                "study_seconds=%d fusion=%s distance_mm=%d raw_distance_mm=%d "
                "tof_ok=%d bj=%s lcd=%d\n"
                % (
                    v1, v2, v1 - v2, pir_value, 1 if present else 0,
                    study_seconds, internal_state,
                    distance_mm if distance_mm is not None else -1,
                    raw_distance_mm if raw_distance_mm is not None else -1,
                    1 if tof_healthy else 0, beijing_time, 1 if lcd_ok else 0,
                )
            )
            state_file.write(
                "pet_stage=%d pet_growth=%d stamina=%d sick=%d "
                "pet_visual=%s daily_study_seconds=%d daily_goal_seconds=%d "
                "daily_goal_percent=%d env_ok=%d\n"
                % (
                    pet_state["stage"], pet_state["growth"],
                    pet_state["stamina"], 1 if pet_state["sick"] else 0,
                    pet_state["visual_state"],
                    pet_state["daily_study_seconds"],
                    pet_state["daily_goal_seconds"],
                    pet_state["daily_goal_percent"],
                    1 if pet_state["environment_ok"] else 0,
                )
            )
    except Exception:
        pass


# OLED and sensors.
i2c = SoftI2C(scl=Pin(5), sda=Pin(4), freq=400_000)
oled = SSD1306(i2c)
light1 = ADC(Pin(6))
light2 = ADC(Pin(7))
for sensor in (light1, light2):
    try:
        sensor.atten(ADC.ATTN_11DB)
    except Exception:
        pass
pir = Pin(16, Pin.IN)
dht11 = dht.DHT11(Pin(15))


# VL53L0X has its own SoftI2C bus so the working OLED bus remains untouched.
tof_i2c = SoftI2C(sda=Pin(17), scl=Pin(18), freq=100_000)
tof = None
tof_error = ""
try:
    if 0x29 not in tof_i2c.scan():
        raise RuntimeError("VL53L0X address 0x29 not found")

    # ESP32 reset does not remove power from the sensor. Re-running its init
    # sequence without resetting the VL53L0X can leave it returning 8190/8191.
    # Follow ST's ResetDevice sequence through register 0xBF first.
    tof_i2c.writeto_mem(0x29, 0xBF, b"\x00")
    reset_deadline = time.ticks_add(time.ticks_ms(), 500)
    while tof_i2c.readfrom_mem(0x29, 0xC0, 1)[0] != 0:
        if time.ticks_diff(reset_deadline, time.ticks_ms()) <= 0:
            raise RuntimeError("VL53L0X reset-low timeout")
        time.sleep_ms(2)
    tof_i2c.writeto_mem(0x29, 0xBF, b"\x01")
    reset_deadline = time.ticks_add(time.ticks_ms(), 500)
    while tof_i2c.readfrom_mem(0x29, 0xC0, 1)[0] == 0:
        if time.ticks_diff(reset_deadline, time.ticks_ms()) <= 0:
            raise RuntimeError("VL53L0X boot timeout")
        time.sleep_ms(2)

    tof = VL53L0X(tof_i2c, address=0x29, io_timeout_ms=500)
    tof.start_continuous()
except Exception as exc:
    tof_error = repr(exc)
    try:
        with open("/tof_error.txt", "w") as error_file:
            error_file.write(tof_error)
    except Exception:
        pass


# The kit routes ST7789 signals as SCK=21, MOSI=47, DC=43, CS=44.
# GPIO43/GPIO44 also carry UART0, so the LCD takes control after the grace window.
lcd = None
lcd_fb = None
lcd_buffer = None
lcd_error = ""
try:
    lcd_spi = SPI(
        1,
        baudrate=31_250_000,
        polarity=0,
        phase=0,
        sck=Pin(21, Pin.OUT),
        mosi=Pin(47, Pin.OUT),
        miso=None,
    )
    lcd = ST7789(lcd_spi, dc=Pin(43, Pin.OUT), cs=Pin(44, Pin.OUT), rotation=0)
    lcd_buffer = bytearray(240 * 240 * 2)
    lcd_fb = framebuf.FrameBuffer(lcd_buffer, 240, 240, framebuf.RGB565)
    lcd_fb.fill(0)
    lcd.show(lcd_buffer)
except Exception as exc:
    lcd_error = repr(exc)
    try:
        with open("/lcd_error.txt", "w") as error_file:
            error_file.write(lcd_error)
    except Exception:
        pass


WHITE = 0xFFFF
BLACK = 0x0000
lcd_static = None
lcd_normal_sprite = None
lcd_normal_animation_sprites = []
lcd_sick_sprites = []
lcd_evolved_sprites = []
if lcd is not None:
    draw_lcd_static(lcd_fb, BLACK, WHITE)
    lcd_static = bytes(lcd_buffer)
    lcd_normal_sprite = load_binary("/normal.rgb565")
    for frame_number in range(4):
        lcd_normal_animation_sprites.append(
            load_binary("/normal_%d.rgb565" % frame_number)
        )
        lcd_sick_sprites.append(
            load_binary("/sick_%d.rgb565" % frame_number)
        )
        lcd_evolved_sprites.append(
            load_binary("/evolved_%d.rgb565" % frame_number)
        )
    lcd_buffer[:] = lcd_static
    blit_pet_sprite(lcd_buffer, lcd_normal_sprite)
    lcd.show(lcd_buffer)

# NORMAL stays on the original still sprite.  Once per minute it performs one
# four-frame jump (crouch -> rise -> apex -> land), then returns to stillness.
NORMAL_ANIMATION_INTERVAL_MS = 60_000
NORMAL_ANIMATION_FRAME_MS = 220
NORMAL_ANIMATION_DURATION_MS = NORMAL_ANIMATION_FRAME_MS * 4
normal_animation_started_at = None
last_normal_animation_at = time.ticks_ms()

last_state_save = None
tracker = FusionPresenceTracker(
    enter_distance_mm=850,
    exit_distance_mm=1000,
    enter_confirm_ms=500,
    motion_event_window_ms=8000,
    exit_invalid_confirm_ms=3000,
    pir_fallback_ms=90000,
)
pet_system = PetGrowthSystem()
distance_filter = DistanceMedianFilter(
    size=5,
    minimum_mm=150,
    maximum_mm=2000,
    minimum_valid=3,
    maximum_spread_mm=250,
)
tof_error_count = 0
temperature_c = None
humidity_percent = None
last_dht_read = None

while True:
    v1 = sum(read_adc12(light1) for _ in range(8)) // 8
    v2 = sum(read_adc12(light2) for _ in range(8)) // 8
    motion = pir.value()
    now = time.ticks_ms()

    # DHT11 should be sampled no faster than about once every two seconds.
    # Keep the last valid reading if an occasional checksum/timeout occurs.
    if (
        last_dht_read is None
        or time.ticks_diff(now, last_dht_read) >= 2500
    ):
        last_dht_read = now
        try:
            dht11.measure()
            temperature_c = dht11.temperature()
            humidity_percent = dht11.humidity()
        except Exception:
            pass

    measured_mm = None
    raw_distance_mm = None
    if tof is not None:
        try:
            measured_mm = tof.range
            tof_error_count = 0
            # 8190/8191 are out-of-range sentinel readings, not desk distance.
            if 20 <= measured_mm <= 2000:
                raw_distance_mm = measured_mm
        except Exception as exc:
            tof_error_count += 1
            tof_error = repr(exc)

    tof_healthy = tof is not None and tof_error_count < 5
    distance_mm = distance_filter.update(
        raw_distance_mm, now, time.ticks_diff
    )
    presence = tracker.update(
        motion, distance_mm, tof_healthy, now, time.ticks_diff
    )
    study_seconds = presence["study_seconds"]
    motion_hours = study_seconds // 3600
    motion_minutes = (study_seconds % 3600) // 60
    motion_secs = study_seconds % 60
    duration_text = "%02d:%02d:%02d" % (
        min(motion_hours, 99), motion_minutes, motion_secs
    )

    clock = time.localtime()
    beijing_time = "%02d:%02d:%02d" % (clock[3], clock[4], clock[5])
    day_key = "%04d-%02d-%02d" % (clock[0], clock[1], clock[2])
    light_average = (v1 + v2) // 2
    pet_state = pet_system.update(
        presence["present"], study_seconds, light_average, distance_mm,
        now, day_key, time.ticks_diff,
    )

    # OLED: Beijing time, fused child presence, session time and distance.
    oled.fill(0)
    oled.text("BJ " + beijing_time, 16, 0, 1)
    child_line = "CHILD: " + ("PRESENT" if presence["present"] else "AWAY")
    oled.text(child_line, max(0, (128 - len(child_line) * 8) // 2), 16, 1)
    timer_label = "STUDY " if presence["present"] else "LAST  "
    timer_line = timer_label + duration_text
    oled.text(timer_line, max(0, (128 - len(timer_line) * 8) // 2), 32, 1)
    if presence["present"] and distance_mm is not None:
        distance_text = "%03dcm" % min(999, distance_mm // 10)
    else:
        distance_text = "---"
    sensor_line = "DIST: " + distance_text
    oled.text(sensor_line, max(0, (128 - len(sensor_line) * 8) // 2), 48, 1)
    oled.show()

    # LCD: normal/evolved/sick pet animation plus study/environment stats.
    if lcd is not None:
        visual_state = pet_state["visual_state"]
        if visual_state == "SICK":
            # Wait a full minute after recovery before the next normal jump.
            normal_animation_started_at = None
            last_normal_animation_at = now
            animation_frame = (now // 500) % 4
            pet_sprite = lcd_sick_sprites[animation_frame]
            pet_title = "PET SICK"
            pet_name = "SICK"
        elif visual_state == "EVOLVED":
            normal_animation_started_at = None
            last_normal_animation_at = now
            animation_frame = (now // 400) % 4
            pet_sprite = lcd_evolved_sprites[animation_frame]
            pet_title = "PET HAPPY"
            pet_name = "HAPPY"
        else:
            if (
                normal_animation_started_at is None
                and time.ticks_diff(now, last_normal_animation_at)
                >= NORMAL_ANIMATION_INTERVAL_MS
            ):
                normal_animation_started_at = now
                last_normal_animation_at = now

            if normal_animation_started_at is not None:
                animation_elapsed = time.ticks_diff(
                    now, normal_animation_started_at
                )
                if animation_elapsed < NORMAL_ANIMATION_DURATION_MS:
                    animation_frame = min(
                        3, animation_elapsed // NORMAL_ANIMATION_FRAME_MS
                    )
                    pet_sprite = lcd_normal_animation_sprites[
                        animation_frame
                    ]
                else:
                    normal_animation_started_at = None
                    pet_sprite = lcd_normal_sprite
            else:
                pet_sprite = lcd_normal_sprite
            pet_title = "PET NORMAL"
            pet_name = "MOMO"
        lcd_buffer[:] = lcd_static
        if not blit_pet_sprite(lcd_buffer, pet_sprite):
            scaled_text(lcd_fb, "PET", 51, 76, 2, WHITE)
        light_percent = min(100, light_average * 100 // 4095)

        lcd_fb.text(pet_title, 8, 9, WHITE)
        pet_name_x = max(1, (146 - len(pet_name) * 16) // 2)
        scaled_text(lcd_fb, pet_name, pet_name_x, 156, 2, WHITE)

        daily_seconds = pet_state["daily_study_seconds"]
        daily_text = "%02d:%02d:%02d" % (
            min(99, daily_seconds // 3600),
            (daily_seconds % 3600) // 60,
            daily_seconds % 60,
        )
        lcd_fb.text("TODAY " + daily_text, 17, 184, WHITE)
        goal_seconds = pet_state["daily_goal_seconds"]
        goal_text = "%02d:%02d" % (
            min(99, goal_seconds // 3600),
            (goal_seconds % 3600) // 60,
        )
        lcd_fb.text(
            "GOAL %s %3d%%" % (
                goal_text, pet_state["daily_goal_percent"]
            ),
            13, 202, WHITE,
        )
        bottom_message = pet_state["event"]
        if not bottom_message:
            if not presence["present"]:
                bottom_message = "RESTING"
            elif pet_state["environment_ok"]:
                bottom_message = "ENV OK"
            else:
                bottom_message = "ADJUST ENV"
        message_x = max(1, (146 - len(bottom_message) * 8) // 2)
        lcd_fb.text(bottom_message, message_x, 222, WHITE)

        lcd_fb.text("%3d" % pet_state["stamina"], 200, 30, WHITE)
        stamina_width = 56 * pet_state["stamina"] // 100
        if stamina_width:
            lcd_fb.fill_rect(166, 46, stamina_width, 6, WHITE)
        lcd_fb.text("%3d" % pet_state["growth"], 200, 62, WHITE)
        growth_width = 56 * min(81, pet_state["growth"]) // 81
        if growth_width:
            lcd_fb.fill_rect(166, 78, growth_width, 6, WHITE)

        lcd_fb.text(daily_text, 162, 110, WHITE)
        lcd_fb.text(
            "L%3d%% %s" % (
                light_percent, "OK" if pet_state["light_ok"] else "!!"
            ),
            164, 138, WHITE,
        )
        if distance_mm is None:
            distance_line = "D --- --"
        else:
            distance_line = "D%3d %s" % (
                min(999, distance_mm // 10),
                "OK" if pet_state["distance_ok"] else "!!",
            )
        lcd_fb.text(distance_line, 164, 158, WHITE)
        presence_text = "PRESENT" if presence["present"] else "AWAY"
        presence_x = 194 - len(presence_text) * 4
        lcd_fb.text(presence_text, presence_x, 202, WHITE)
        lcd.show(lcd_buffer)

    if (
        presence["transition"]
        or last_state_save is None
        or time.ticks_diff(now, last_state_save) >= 60_000
    ):
        save_state(
            v1, v2, motion, presence["present"], study_seconds,
            presence["internal_state"], distance_mm, raw_distance_mm,
            tof_healthy, lcd is not None, beijing_time, pet_state,
        )
        last_state_save = now

    time.sleep_ms(200)
