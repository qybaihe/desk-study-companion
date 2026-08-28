"""Desk companion display app.

240x240 ST7789 LCD: persistent pet cultivation, growth and environment.
128x64 SSD1306 OLED: Beijing time, light, temperature and humidity.
"""

import dht
import framebuf
import machine
import ntptime
import os
import time
from machine import ADC, Pin, SoftI2C, SPI, WDT
from audio_manager import AudioManager
from fusion_tracker import DistanceMedianFilter, FusionPresenceTracker
from pet_animation import LoopingFrameAnimator, OneShotFrameAnimator
from pet_growth import PetGrowthSystem
from st7789 import ST7789
from study_reminder import LowLightReminder, OneShotStudyReminder
from vl53l0x import VL53L0X
from voice_device_actions import VoiceDeviceActionHandler
from voice_qa_client import VoiceQAClient


# ESP32-S3 maximum supported CPU clock.  Setting it before display/sensor
# initialization also makes asset decoding and framebuffer work deterministic.
try:
    machine.freq(240_000_000)
except Exception:
    pass
CPU_FREQUENCY_MHZ = machine.freq() // 1_000_000


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
    target.text("STUDY", 174, 96, white)
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
    pet_state, normal_jump_count, normal_jump_frame, normal_jump_assets_ok,
    normal_jump_duration_ms,
    water_reminder_played, voice_playing, voice_play_count, voice_error,
    low_light_armed, low_light_play_count, pending_voice_count,
    qa_state, qa_wifi, qa_ip, qa_question_count, qa_error,
    clock_synced,
):
    try:
        with open("/state.txt", "w") as state_file:
            state_file.write(
                "v1=%d v2=%d diff=%d pir=%d present=%d "
                "study_seconds=%d fusion=%s distance_mm=%d raw_distance_mm=%d "
                "tof_ok=%d bj=%s clock_synced=%d lcd=%d cpu_mhz=%d\n"
                % (
                    v1, v2, v1 - v2, pir_value, 1 if present else 0,
                    study_seconds, internal_state,
                    distance_mm if distance_mm is not None else -1,
                    raw_distance_mm if raw_distance_mm is not None else -1,
                    1 if tof_healthy else 0, beijing_time,
                    1 if clock_synced else 0, 1 if lcd_ok else 0,
                    CPU_FREQUENCY_MHZ,
                )
            )
            state_file.write(
                "pet_stage=%d pet_growth=%d stamina=%d sick=%d "
                "pet_visual=%s daily_study_seconds=%d daily_goal_seconds=%d "
                "daily_goal_percent=%d daily_goal_growth=%d/%d "
                "env_ok=%d jump_count=%d "
                "jump_frame=%d jump_assets=%d jump_duration_ms=%d\n"
                % (
                    pet_state["stage"], pet_state["growth"],
                    pet_state["stamina"], 1 if pet_state["sick"] else 0,
                    pet_state["visual_state"],
                    pet_state["daily_study_seconds"],
                    pet_state["daily_goal_seconds"],
                    pet_state["daily_goal_percent"],
                    pet_state["daily_goal_growth_awarded"],
                    pet_state["daily_goal_growth_max"],
                    1 if pet_state["environment_ok"] else 0,
                    normal_jump_count, normal_jump_frame,
                    1 if normal_jump_assets_ok else 0,
                    normal_jump_duration_ms,
                )
            )
            safe_voice_error = (voice_error or "-").replace(" ", "_")
            safe_voice_error = safe_voice_error.replace("\n", "_")
            state_file.write(
                "water_reminder=%d voice_playing=%d voice_play_count=%d "
                "voice_error=%s low_light_armed=%d low_light_count=%d "
                "voice_queue=%d\n"
                % (
                    1 if water_reminder_played else 0,
                    1 if voice_playing else 0,
                    voice_play_count,
                    safe_voice_error,
                    1 if low_light_armed else 0,
                    low_light_play_count,
                    pending_voice_count,
                )
            )
            safe_qa_error = (qa_error or "-").replace(" ", "_")
            safe_qa_error = safe_qa_error.replace("\n", "_")
            state_file.write(
                "voice_qa_state=%s voice_qa_wifi=%d voice_qa_ip=%s "
                "voice_qa_questions=%d voice_qa_error=%s\n"
                % (
                    qa_state,
                    1 if qa_wifi else 0,
                    qa_ip,
                    qa_question_count,
                    safe_qa_error,
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

# Button-Pulldown1 is active-high on IO10. LED2 uses the neighboring free
# IO9 signal row and mirrors the button immediately on both edges.
button_pulldown1 = Pin(10, Pin.IN, Pin.PULL_DOWN)
led2 = Pin(9, Pin.OUT, value=0)


def mirror_button_to_led2(button_pin):
    led2.value(button_pin.value())


button_pulldown1.irq(
    trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING,
    handler=mirror_button_to_led2,
)
mirror_button_to_led2(button_pulldown1)


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
    try:
        os.remove("/tof_error.txt")
    except OSError:
        pass
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
        baudrate=40_000_000,
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
    try:
        os.remove("/lcd_error.txt")
    except OSError:
        pass
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
lcd_low_light_sprites = []
lcd_rest_break_sprites = []
if lcd is not None:
    draw_lcd_static(lcd_fb, BLACK, WHITE)
    lcd_static = bytes(lcd_buffer)
    lcd_normal_sprite = load_binary("/normal.rgb565")
    for frame_number in range(48):
        lcd_normal_animation_sprites.append(
            load_binary("/normal_%d.rgb565" % frame_number)
        )
    for frame_number in range(4):
        lcd_sick_sprites.append(
            load_binary("/sick_%d.rgb565" % frame_number)
        )
        lcd_evolved_sprites.append(
            load_binary("/evolved_%d.rgb565" % frame_number)
        )
    for frame_number in range(8):
        lcd_low_light_sprites.append(
            load_binary("/low_light_%d.rgb565" % frame_number)
        )
        lcd_rest_break_sprites.append(
            load_binary("/rest_break_%d.rgb565" % frame_number)
        )
    normal_jump_assets_ok = (
        lcd_normal_sprite is not None
        and len(lcd_normal_sprite) == 136 * 112 * 2
        and len(lcd_normal_animation_sprites) == 48
        and all(
            sprite is not None and len(sprite) == 136 * 112 * 2
            for sprite in lcd_normal_animation_sprites
        )
    )
    low_light_animation_assets_ok = (
        len(lcd_low_light_sprites) == 8
        and all(
            sprite is not None and len(sprite) == 136 * 112 * 2
            for sprite in lcd_low_light_sprites
        )
    )
    rest_break_animation_assets_ok = (
        len(lcd_rest_break_sprites) == 8
        and all(
            sprite is not None and len(sprite) == 136 * 112 * 2
            for sprite in lcd_rest_break_sprites
        )
    )
    lcd_buffer[:] = lcd_static
    blit_pet_sprite(lcd_buffer, lcd_normal_sprite)
    lcd.show(lcd_buffer)

# NORMAL plays a 48-frame, two-second jump every 60 seconds.  SICK and EVOLVED
# disable it; after returning to NORMAL it waits a fresh 60 seconds.
NORMAL_ANIMATION_INTERVAL_MS = 60_000
NORMAL_ANIMATION_FRAME_DURATIONS_MS = (
    42, 42, 41, 42, 42, 41, 42, 42, 41, 42, 42, 41,
    42, 42, 41, 42, 42, 41, 42, 42, 41, 42, 42, 41,
    42, 42, 41, 42, 42, 41, 42, 42, 41, 42, 42, 41,
    42, 42, 41, 42, 42, 41, 42, 42, 41, 42, 42, 41,
)
NORMAL_ANIMATION_DURATION_MS = sum(NORMAL_ANIMATION_FRAME_DURATIONS_MS)
normal_animator = OneShotFrameAnimator(
    NORMAL_ANIMATION_FRAME_DURATIONS_MS,
    NORMAL_ANIMATION_INTERVAL_MS,
    time.ticks_ms(),
)
normal_jump_count = 0
normal_jump_frame = -1
if lcd is None:
    normal_jump_assets_ok = False
    low_light_animation_assets_ok = False
    rest_break_animation_assets_ok = False

low_light_voice_animator = LoopingFrameAnimator(
    frame_count=8,
    frame_duration_ms=125,
)
rest_break_voice_animator = LoopingFrameAnimator(
    frame_count=8,
    frame_duration_ms=125,
)

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
water_reminder = OneShotStudyReminder(threshold_seconds=30)
low_light_reminder = LowLightReminder(
    low_threshold=PetGrowthSystem.LIGHT_MIN,
    recovery_threshold=PetGrowthSystem.LIGHT_MIN + 200,
    low_confirm_ms=5000,
    recovery_confirm_ms=10000,
    cooldown_ms=30 * 60_000,
)
voice_player = AudioManager(
    default_path="/drink_water.pcm",
    speaker_rate=16_000,
    speaker_data_pin=38,
    speaker_clock_pin=39,
    speaker_word_select_pin=40,
    microphone_clock_pin=41,
    microphone_word_select_pin=42,
    microphone_data_pin=2,
)
# B10K potentiometer: outer pins to 3V3/GND, centre wiper to GPIO8.
volume_knob = ADC(Pin(8))
volume_knob.atten(ADC.ATTN_11DB)
last_volume_poll = None
voice_qa = VoiceQAClient(voice_player, button_pulldown1)
voice_action_handler = VoiceDeviceActionHandler(pet_system)
voice_queue = []
tof_error_count = 0
temperature_c = None
humidity_percent = None
last_dht_read = None
last_oled_refresh = None
last_background_service = None
previous_present = False
study_session_id = ""
clock_synced = False
next_ntp_attempt = time.ticks_add(time.ticks_ms(), 20_000)

# If a transient I2C/SPI/I2S transaction ever stalls the application, reboot
# automatically instead of leaving both displays frozen indefinitely.
system_watchdog = WDT(timeout=8_000)

while True:
    system_watchdog.feed()
    # Audio and network state advance independently from the comparatively
    # expensive full-frame LCD/sensor work.
    loop_now = time.ticks_ms()
    if (
        last_volume_poll is None
        or time.ticks_diff(loop_now, last_volume_poll) >= 50
    ):
        volume_raw = sum(volume_knob.read() for _ in range(4)) // 4
        voice_player.set_volume_adc(volume_raw)
        last_volume_poll = loop_now
    voice_player.update(loop_now)
    voice_qa.update(loop_now)
    # The authenticated Mac service can attach a deterministic device action
    # to a voice answer. Apply it while the response header is still resident;
    # the handler de-duplicates the many cooperative loops during playback.
    voice_action_handler.consume(getattr(voice_qa, "_response", None))
    discovered_rtc = voice_qa.take_beijing_rtc()
    if discovered_rtc is not None:
        try:
            machine.RTC().datetime(discovered_rtc)
            clock_synced = True
            voice_qa.state_changed = True
        except Exception:
            pass
    elif (
        not clock_synced
        and voice_qa.wifi_connected
        and not voice_qa.busy
        and time.ticks_diff(loop_now, next_ntp_attempt) >= 0
    ):
        # Internet NTP is only a fallback for networks that block both UDP
        # broadcast and the direct last-known Mac discovery probe.
        try:
            ntptime.settime()
            shifted = time.localtime(time.time() + 8 * 3600)
            machine.RTC().datetime(
                (
                    shifted[0], shifted[1], shifted[2], shifted[6],
                    shifted[3], shifted[4], shifted[5], 0,
                )
            )
            clock_synced = True
            voice_qa.state_changed = True
        except Exception:
            next_ntp_attempt = time.ticks_add(loop_now, 60_000)
    voice_qa_changed = voice_qa.consume_state_change()

    # Microphone DMA blocks must be consumed immediately.  During the other
    # voice phases the UI/sensors still refresh at 10 Hz while socket and I2S
    # work continue on every cooperative pass.
    if voice_qa.capture_priority and not voice_qa_changed:
        time.sleep_ms(1)
        continue
    if (
        voice_qa.wants_fast_loop
        and not voice_qa_changed
        and last_background_service is not None
        and time.ticks_diff(loop_now, last_background_service) < 100
    ):
        time.sleep_ms(1)
        continue
    last_background_service = loop_now

    v1 = sum(read_adc12(light1) for _ in range(8)) // 8
    v2 = sum(read_adc12(light2) for _ in range(8)) // 8
    motion = pir.value()
    now = time.ticks_ms()

    # DHT11 should be sampled no faster than about once every two seconds.
    # Keep the last valid reading if an occasional checksum/timeout occurs.
    if (
        not normal_animator.active
        and (
            last_dht_read is None
            or time.ticks_diff(now, last_dht_read) >= 2500
        )
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
    reminder_triggered = water_reminder.update(
        presence["present"], study_seconds
    )
    if reminder_triggered:
        voice_queue.append("/drink_water.pcm")
    motion_hours = study_seconds // 3600
    motion_minutes = (study_seconds % 3600) // 60
    motion_secs = study_seconds % 60
    duration_text = "%02d:%02d:%02d" % (
        min(motion_hours, 99), motion_minutes, motion_secs
    )

    clock = time.localtime()
    beijing_time = "%02d:%02d:%02d" % (clock[3], clock[4], clock[5])
    day_key = "%04d-%02d-%02d" % (clock[0], clock[1], clock[2])
    if presence["present"] and not previous_present:
        study_session_id = "%sT%02d%02d%02d" % (
            day_key, clock[3], clock[4], clock[5]
        )
    previous_present = presence["present"]
    light_average = (v1 + v2) // 2
    light_percent = min(100, light_average * 100 // 4095)
    low_light_triggered = low_light_reminder.update(
        presence["present"], light_average, now, time.ticks_diff
    )
    if low_light_triggered:
        # Lighting guidance has priority if two reminders become ready in the
        # same sensor update; the 30-second break prompt remains queued.
        voice_queue.insert(0, "/light_too_dark.pcm")
    voice_qa.set_context(
        {
            "session_id": study_session_id,
            "beijing_time": day_key + " " + beijing_time,
            "present": bool(presence["present"]),
            "study_seconds": study_seconds,
            "daily_study_seconds": pet_system.daily_study_ms // 1000,
            "daily_goal_seconds": pet_system.daily_goal_seconds,
            "pet_growth": pet_system.growth,
            "distance_mm": distance_mm,
            "pir_motion": bool(motion),
            "light_1": v1,
            "light_2": v2,
            "light_percent": light_percent,
            "temperature_c": temperature_c,
            "humidity_percent": humidity_percent,
            "tof_healthy": bool(tof_healthy),
            "water_reminder_triggered": bool(reminder_triggered),
            "low_light_triggered": bool(low_light_triggered),
        }
    )

    voice_started = False
    if not voice_player.busy and not voice_qa.busy and voice_queue:
        voice_started = voice_player.start(voice_queue.pop(0))
    pet_state = pet_system.update(
        presence["present"], study_seconds, light_average, distance_mm,
        now, day_key, time.ticks_diff,
    )

    # OLED information only needs a 5 Hz refresh.  Avoid sending the same 1 KB
    # buffer on every 24 FPS LCD animation iteration.
    if (
        last_oled_refresh is None
        or time.ticks_diff(now, last_oled_refresh) >= 200
    ):
        oled.fill(0)
        oled.text("BJ " + beijing_time, 16, 0, 1)
        light_line = "LIGHT: %3d%%" % light_percent
        oled.text(
            light_line, max(0, (128 - len(light_line) * 8) // 2), 16, 1
        )
        if temperature_c is None:
            temperature_line = "TEMP: ---C"
        else:
            temperature_line = "TEMP: %3dC" % temperature_c
        oled.text(
            temperature_line,
            max(0, (128 - len(temperature_line) * 8) // 2),
            32,
            1,
        )
        if humidity_percent is None:
            humidity_line = "HUMI: ---%"
        else:
            humidity_line = "HUMI: %3d%%" % humidity_percent
        oled.text(
            humidity_line,
            max(0, (128 - len(humidity_line) * 8) // 2),
            48,
            1,
        )
        oled.show()
        last_oled_refresh = now

    # LCD: normal/evolved/sick pet animation plus study/environment stats.
    jump_started = False
    normal_jump_frame = -1
    if lcd is not None:
        visual_state = pet_state["visual_state"]
        low_light_voice_active = (
            voice_player.playing
            and voice_player.path == "/light_too_dark.pcm"
            and low_light_animation_assets_ok
        )
        rest_break_voice_active = (
            voice_player.playing
            and voice_player.path == "/drink_water.pcm"
            and rest_break_animation_assets_ok
        )
        low_light_voice_animator.update(
            now,
            low_light_voice_active,
            time.ticks_diff,
            time.ticks_add,
        )
        rest_break_voice_animator.update(
            now,
            rest_break_voice_active,
            time.ticks_diff,
            time.ticks_add,
        )
        jump_started = normal_animator.update(
            now,
            visual_state == "NORMAL"
            and normal_jump_assets_ok
            and not low_light_voice_active
            and not rest_break_voice_active
            and not voice_qa.busy,
            time.ticks_diff,
            time.ticks_add,
        )
        normal_jump_count = normal_animator.play_count
        normal_jump_frame = normal_animator.frame
        normal_region_only = normal_animator.active
        voice_state_titles = {
            VoiceQAClient.RECORDING: "RECORDING",
            VoiceQAClient.PROCESSING: "PROCESSING",
            VoiceQAClient.UPLOADING: "UPLOADING",
            VoiceQAClient.THINKING: "THINKING",
            VoiceQAClient.PLAYING: "AI ANSWER",
            VoiceQAClient.ERROR: "VOICE ERROR",
        }
        if voice_qa.state in voice_state_titles:
            pet_sprite = lcd_normal_sprite
            pet_title = voice_state_titles[voice_qa.state]
            pet_name = "MOMO"
            normal_region_only = False
        elif low_light_voice_active:
            pet_sprite = lcd_low_light_sprites[
                low_light_voice_animator.frame
            ]
            pet_title = "LAMP ALERT"
            pet_name = "MOMO"
        elif rest_break_voice_active:
            pet_sprite = lcd_rest_break_sprites[
                rest_break_voice_animator.frame
            ]
            pet_title = "BREAK TIME"
            pet_name = "MOMO"
        elif visual_state == "SICK":
            animation_frame = (now // 500) % 4
            pet_sprite = lcd_sick_sprites[animation_frame]
            pet_title = "PET SICK"
            pet_name = "SICK"
        elif visual_state == "EVOLVED":
            animation_frame = (now // 400) % 4
            pet_sprite = lcd_evolved_sprites[animation_frame]
            pet_title = "PET HAPPY"
            pet_name = "HAPPY"
        else:
            if normal_animator.active:
                pet_sprite = lcd_normal_animation_sprites[
                    normal_animator.frame
                ]
            else:
                pet_sprite = lcd_normal_sprite
            pet_title = "PET NORMAL"
            pet_name = "MOMO"
        lcd_buffer[:] = lcd_static
        if not blit_pet_sprite(lcd_buffer, pet_sprite):
            scaled_text(lcd_fb, "PET", 51, 76, 2, WHITE)
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
        volume_text = "VOL %3d%%" % voice_player.volume_percent
        lcd_fb.text(
            volume_text,
            max(7, (150 - len(volume_text) * 8) // 2),
            220,
            WHITE,
        )
        lcd_fb.text("%3d" % pet_state["stamina"], 200, 30, WHITE)
        stamina_width = 56 * pet_state["stamina"] // 100
        if stamina_width:
            lcd_fb.fill_rect(166, 46, stamina_width, 6, WHITE)
        lcd_fb.text("%3d" % pet_state["growth"], 200, 62, WHITE)
        growth_width = 56 * min(81, pet_state["growth"]) // 81
        if growth_width:
            lcd_fb.fill_rect(166, 78, growth_width, 6, WHITE)

        # The right STATS time is the current continuous study session.  The
        # left-side TODAY line remains the only daily cumulative time display.
        lcd_fb.text(duration_text, 162, 110, WHITE)
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
        if normal_region_only:
            # The pet occupies only 26% of the panel.  A region transfer sends
            # 30,464 bytes instead of 115,200, removing the main FPS bottleneck.
            lcd.show_region(pet_sprite, 7, 36, 136, 112)
        else:
            lcd.show(lcd_buffer)

    if (
        presence["transition"]
        or jump_started
        or normal_animator.just_completed
        or reminder_triggered
        or low_light_triggered
        or voice_started
        or voice_qa_changed
        or last_state_save is None
        or time.ticks_diff(now, last_state_save) >= 60_000
    ):
        save_state(
            v1, v2, motion, presence["present"], study_seconds,
            presence["internal_state"], distance_mm, raw_distance_mm,
            tof_healthy, lcd is not None, beijing_time, pet_state,
            normal_jump_count, normal_jump_frame, normal_jump_assets_ok,
            normal_animator.last_duration_ms,
            water_reminder.played, voice_player.playing,
            voice_player.play_count, voice_player.error,
            low_light_reminder.armed, low_light_reminder.play_count,
            len(voice_queue),
            voice_qa.state, voice_qa.wifi_connected, voice_qa.wifi_ip,
            voice_qa.question_count, voice_qa.error,
            clock_synced,
        )
        last_state_save = now

    # Increase refresh precision only during the two-second normal jump.  Idle
    # operation remains at 5 Hz to keep I2C/SPI traffic and power consumption
    # low, while every animation frame is now rendered at least once.
    time.sleep_ms(
        1 if voice_qa.wants_fast_loop or normal_animator.active else (
            10 if voice_player.playing else 200
        )
    )
