"""网络韧性层：断线自动重连 + 离线落盘 + 批量补传 + 配置下行。

设计要点
  1. 绝不阻塞主循环。传感器采集和屏幕刷新必须一直跑，网络慢不能拖累它们。
     实测板子到 Cloudflare 一次 TLS 上报要 7~21 秒，而主循环的看门狗只有
     8 秒 —— 直接在循环里发请求，板子必然重启。所以上报跑在独立线程里，
     主循环只负责把样本丢进队列。
  2. 断网时样本写 SD 卡，联网后按顺序补传。比赛现场 Wi-Fi 一定不稳，
     没有这一条演示会很难看。
  3. 上报响应里带回配置和家长的待办动作，比对 rev 就地生效 ——
     不需要额外连接或协议。
  4. 空闲时每 POLL_SECONDS 轻量拉一次 /pull。家长在 App 上按"喂一把草"，
     到小羊有反应最多等这么久；靠 60 秒的上报周期太慢了。
"""
import network, time, ujson, os, gc, _thread

try:
    import urequests as requests
except ImportError:
    import requests


SPOOL = "/sd/spool"          # SD 卡：IO3=CLK, IO14=MOSI, IO35=MISO, IO46=CS
FALLBACK_SPOOL = "/spool"    # 没插卡时退回内部 flash（容量小，只当兜底）


def utc_stamp(secs=None):
    """把板子的北京时 RTC 换算成库里要的 UTC 字符串。

    Worker 那边所有的"今天"、"最后同步"都按 UTC 存、+8 显示。
    板子要是直接发北京时间，会整整错开 8 小时 —— 晚上八点的数据
    会被算进第二天。
    """
    t = time.localtime((secs if secs is not None else time.time()) - 8 * 3600)
    return "%04d-%02d-%02d %02d:%02d:00" % (t[0], t[1], t[2], t[3], t[4])


def _spool_dir():
    for d in (SPOOL, FALLBACK_SPOOL):
        try:
            os.listdir(d.rsplit("/", 1)[0] or "/")
            try: os.mkdir(d)
            except OSError: pass
            return d
        except OSError:
            continue
    return None


class Net:
    def __init__(self, ssid, password, base_url, device_id, child_id,
                 batch_seconds=45, token=None, feed=None):
        self.ssid, self.password = ssid, password
        self.base = base_url.rstrip("/")
        self.device_id, self.child_id = device_id, child_id
        self.batch_seconds = batch_seconds
        self.token = token
        # 主循环有 8 秒看门狗，而一次 TLS 握手可能要好几秒。
        # 把喂狗回调传进来，在请求前后各喂一次，避免上报把板子搞重启。
        self.feed = feed or (lambda: None)
        self.wlan = network.WLAN(network.STA_IF)
        self.wlan.active(True)
        try:
            self.wlan.config(reconnects=-1)  # 底层无限重连
        except OSError:
            # 接口刚被别人动过时会抛 "Wifi Internal State Error"。
            # 这只是个优化项，失败了不该让整个上行层建不起来。
            pass
        self._buf = []
        self._last_flush = time.time()
        self._backoff = 1
        self._next_try = 0
        self.config = {}
        self.config_rev = -1
        self.online = False
        self.spool = _spool_dir()
        self._busy = False        # 上报线程是否在跑，同一时刻只允许一个
        self.clock_ok = False     # RTC 对上表了没有
        self.actions = []         # 家长按下来的一次性动作，主循环取走
        self._asks = []           # 待上报的问答，最多攒 8 条
        self.message = None       # 家长捎的话，主循环取走后在 OLED 上显示十秒
        self.audio_ready = None   # 语音下好了的文件路径，主循环取走去播
        self.study_seconds = 0    # 板子自己的当日在座秒数，跟着上报一起走
        self.poll_seconds = 20
        self._last_contact = 0
        # 小羊的当前状态，跟着每批样本一起上去。App 首页直接读这三个。
        self.hp, self.grow, self.form = 100, 0, "normal"

    # ---------------- Wi-Fi ----------------

    def pump(self):
        """每轮主循环调一次。非阻塞，最多花几毫秒。"""
        if self.wlan.isconnected():
            if not self.online:
                self.online = True
                self._backoff = 1
                print("wifi up:", self.wlan.ifconfig()[0])
            return True
        self.online = False
        now = time.time()
        if now < self._next_try:
            return False
        try:
            self.wlan.connect(self.ssid, self.password)
        except OSError:
            pass
        self._backoff = min(self._backoff * 2, 30)   # 指数退避，封顶 30 秒
        self._next_try = now + self._backoff
        return False

    # ---------------- 对表 ----------------

    def ensure_clock(self):
        """非阻塞。对上表之前每次调用都会在后台再试一次。

        对表本身可能很慢：NTP 不通要等超时，退回问 Worker 又是一次 TLS。
        主循环的看门狗只有 8 秒，所以这里也不能同步做。
        """
        if self.clock_ok or self._busy or not self.online:
            return self.clock_ok
        self._start(self._sync_worker)
        return False

    def _sync_worker(self):
        self.clock_ok = self.sync_clock()

    def sync_clock(self):
        """把 RTC 设成北京时间。先试 NTP，不通就问 Worker 要。

        国内网络常挡 UDP 123，NTP 会 ETIMEDOUT；而上报用的这条 HTTPS
        本来就要通。所以拿 Worker 的时间兜底 —— 反正它已经是可信来源了。
        """
        self.feed()
        try:
            import ntptime
            # pool.ntp.org 在国内经常不通，换成阿里云的
            ntptime.host = "ntp.aliyun.com"
            ntptime.settime()
            self._set_rtc_from_utc(time.localtime())
            print("clock: ntp ok")
            return True
        except Exception as exc:
            print("clock: ntp failed:", exc)

        self.feed()
        for attempt in range(2):     # 这条链路上 ECONNRESET 是常态，值得再试一次
            r = None
            try:
                r = requests.get(self.base + "/time", headers=self._headers(),
                                 timeout=25)
                now = r.json()["now"]    # "YYYY-MM-DD HH:MM:SS" UTC
                self._set_rtc_from_utc((
                    int(now[0:4]), int(now[5:7]), int(now[8:10]),
                    int(now[11:13]), int(now[14:16]), int(now[17:19]), 0, 0))
                print("clock: worker ok", now, "UTC")
                return True
            except Exception as exc:
                print("clock: worker failed:", exc)
            finally:
                if r:
                    try: r.close()
                    except Exception: pass
                gc.collect()
            if attempt == 0:
                time.sleep(2)
        return False

    @staticmethod
    def _set_rtc_from_utc(utc_tuple):
        """RTC 存北京时间（主程序和 OLED 都按本地时读），所以 +8 再写。"""
        import machine
        secs = time.mktime(tuple(utc_tuple)) + 8 * 3600
        b = time.localtime(secs)
        machine.RTC().datetime((b[0], b[1], b[2], b[6], b[3], b[4], b[5], 0))

    # ---------------- 上报 ----------------

    def add(self, sample: dict):
        """加一条 60 秒聚合样本。攒够时间再发 —— TLS 握手开销远大于传输本身。"""
        self._buf.append(sample)
        if time.time() - self._last_flush >= self.batch_seconds:
            self.flush()

    def flush(self):
        """把当前批次交给后台线程发。这个函数本身立刻返回。"""
        self._last_flush = time.time()
        if self._busy:
            return                            # 上一批还在发，样本继续攒着
        if not self._buf:
            if self.online:
                self._start(self._drain_spool)
            return
        batch, self._buf = self._buf, []
        self._start(self._send, batch)

    def _start(self, fn, *args):
        self._busy = True
        try:
            _thread.start_new_thread(self._run, (fn, args))
        except Exception as exc:              # 线程起不来就退回同步发
            print("uplink thread failed:", exc)
            self._busy = False
            fn(*args)

    def _run(self, fn, args):
        try:
            fn(*args)
        except Exception as exc:
            print("uplink worker crashed:", exc)
        finally:
            self._busy = False
            gc.collect()

    def _send(self, batch):
        # 手机热点上 ECONNRESET / ETIMEDOUT 是常态，实测五次里会中一次。
        # 在线程里直接重试一次比落盘再等一整个批次周期划算得多。
        for attempt in range(2):
            if not self.online:
                break
            if self._post(batch):
                self._drain_spool()
                return
            if attempt == 0:
                time.sleep(2)
        self._spool_write(batch)              # 还是不行就落盘，绝不丢

    def _headers(self):
        h = {"Content-Type": "application/json",
             # 不带 User-Agent 的请求会被 Cloudflare 边缘挡成 403，
             # 而 urequests 默认什么都不带。这一行是必需的，不是装饰。
             "User-Agent": "sheepy-esp32/1.0"}
        if self.token:
            h["Authorization"] = "Bearer " + self.token
        return h

    def _post(self, samples) -> bool:
        body = {"device_id": self.device_id, "child_id": self.child_id,
                "firmware": "sheepy-1.0", "samples": samples,
                "hp": self.hp, "grow": self.grow, "form": self.form,
                # 板子自己按毫秒累加的当日时长。App 那边原来是按分钟数格子，
                # 同一天能差三成 —— 孩子看 LCD、家长看手机，两块屏得说同一个数。
                "study_seconds": self.study_seconds}
        r = None
        self.feed()
        try:
            r = requests.post(self.base + "/ingest",
                              headers=self._headers(),
                              data=ujson.dumps(body),
                              timeout=25)
            if r.status_code // 100 != 2:
                return False
            self._take(r.json())
            return True
        except Exception as e:
            print("post failed:", e)
            return False
        finally:
            if r:
                try: r.close()
                except Exception: pass
            gc.collect()
            self.feed()

    def _maybe_resync(self, server_utc):
        """服务器时间和板子差超过 2 分钟就重设 RTC。板子的晶振会漂。"""
        if not server_utc:
            return
        try:
            want = time.mktime((
                int(server_utc[0:4]), int(server_utc[5:7]), int(server_utc[8:10]),
                int(server_utc[11:13]), int(server_utc[14:16]),
                int(server_utc[17:19]), 0, 0))
            have = time.time() - 8 * 3600          # 板子 RTC 是北京时
            if abs(want - have) > 120:
                self._set_rtc_from_utc(time.localtime(want))
                print("clock: resynced, drift was", want - have, "s")
        except Exception:
            pass

    # ---------------- 离线缓存 ----------------

    def _spool_write(self, batch):
        if not self.spool:
            return
        try:
            name = "%s/%d.json" % (self.spool, time.ticks_ms())
            with open(name, "w") as f:
                ujson.dump(batch, f)
        except Exception as e:
            print("spool write failed:", e)

    def _drain_spool(self, max_files=3):
        """每次最多补传几个文件，避免一次性把主循环卡住。"""
        if not self.spool or not self.online:
            return
        try:
            files = sorted(os.listdir(self.spool))[:max_files]
        except OSError:
            return
        for name in files:
            path = self.spool + "/" + name
            try:
                with open(path) as f:
                    batch = ujson.load(f)
            except Exception:
                os.remove(path)
                continue
            if self._post(batch):
                os.remove(path)
            else:
                break        # 还是发不出去，下次再说

    # ---------------- 配置下行 ----------------

    def _take(self, body_in):
        """把响应里的配置和动作收下来。上报和轮询走同一套。"""
        self._apply_config(body_in.get("config"))
        self._maybe_resync(body_in.get("now"))
        for a in body_in.get("actions") or []:
            kind = a.get("kind")
            if kind:
                self.actions.append(kind)
        m = body_in.get("message")
        if m and m.get("text"):
            self.message = m      # 一次只留一条 —— 十秒的展示窗口排不了队
        self._last_contact = time.time()

    AUDIO_PATH = "/msg.pcm"

    def fetch_audio(self, path):
        """把 Worker 合成好的裸 PCM 下到 flash。

        16kHz 单声道 16bit，一句话大概 90KB。板子这条 TLS 本来就慢，
        所以整个下载跑在后台线程里，主循环一秒都不等。
        """
        if self._busy or not self.online:
            return
        self._start(self._pull_audio, path)

    def _pull_audio(self, path):
        r = None
        self.feed()
        try:
            r = requests.get(self.base + path, headers=self._headers(), timeout=45)
            if r.status_code // 100 != 2:
                print("audio http", r.status_code)
                return
            data = r.content
            if len(data) < 3200:            # 不到 0.1 秒，多半是出错了
                print("audio too small:", len(data))
                return
            with open(self.AUDIO_PATH, "wb") as f:
                f.write(data)
            self.audio_ready = self.AUDIO_PATH
            print("audio ready:", len(data), "bytes")
        except Exception as exc:
            print("audio fetch failed:", exc)
        finally:
            if r:
                try: r.close()
                except Exception: pass
            gc.collect()
            self.feed()

    def take_audio(self):
        p, self.audio_ready = self.audio_ready, None
        return p

    def take_message(self):
        """主循环取走捎话。取完就清空。"""
        m, self.message = self.message, None
        return m

    def take_actions(self):
        """主循环取走待办动作。取完就清空。"""
        if not self.actions:
            return []
        got, self.actions = self.actions, []
        return got

    def push_state(self):
        """不带样本，只把当前的 hp/grow/form 立刻推上去。

        家长按完喂草，动作 20 秒内就在板子上生效了，但新数值要等下一次
        60 秒的批量上报才回得到手机 —— 中间那一分钟家长会以为没按到。
        """
        if self._busy or not self.online:
            return
        self._start(self._send, [])

    def report_ask(self, question, answer=""):
        """把一轮语音问答排进上报队列。

        板子已经有转写和答案两段文本（它自己调的 MiMo），只是从来没往
        库里写过 —— ask_log 一直是空的，所以手机上的「提问」页什么都看不到。
        """
        q = (question or "").strip()
        if not q:
            return
        if len(self._asks) >= 8:      # 攒太多说明网一直不通，丢最老的
            self._asks.pop(0)
        self._asks.append((q, (answer or "").strip()))

    def pump_ask(self):
        """非阻塞。有待报的就交给后台线程发。

        一次 TLS 握手 2~3 秒，主循环的看门狗只有 8 秒 —— 不能同步发。
        """
        if self._busy or not self.online or not self._asks:
            return
        self._start(self._send_ask, self._asks.pop(0))

    def _send_ask(self, item, tries=0):
        q, a = item
        r = None
        self.feed()
        try:
            r = requests.post(
                self.base + "/api/ask", headers=self._headers(),
                data=ujson.dumps({"device_id": self.device_id,
                                  "child_id": self.child_id,
                                  "question": q, "answer": a}),
                timeout=25)
            if r.status_code // 100 != 2:
                raise RuntimeError("ask %d" % r.status_code)
            print("ask reported:", q[:20])
        except Exception as exc:
            print("ask report failed:", exc)
            if tries < 1:             # 只重排一次，别把队列堵死
                self._asks.insert(0, item)
        finally:
            if r:
                try: r.close()
                except Exception: pass
            gc.collect()
            self.feed()

    def poll(self):
        """空闲时的轻量拉取。非阻塞，实际请求在后台线程里发。"""
        if self._busy or not self.online:
            return
        if time.time() - self._last_contact < self.poll_seconds:
            return
        self._last_contact = time.time()      # 先占住，避免连着起好几个
        self._start(self._pull)

    def _pull(self):
        r = None
        self.feed()
        try:
            r = requests.get(
                "%s/pull?child_id=%s" % (self.base, self.child_id),
                headers=self._headers(), timeout=25)
            if r.status_code // 100 == 2:
                self._take(r.json())
        except Exception as exc:
            print("pull failed:", exc)
        finally:
            if r:
                try: r.close()
                except Exception: pass
            gc.collect()
            self.feed()

    def _apply_config(self, cfg):
        if not cfg:
            return
        rev = cfg.get("rev", 0)
        if rev == self.config_rev:
            return
        self.config = cfg
        self.config_rev = rev
        try:
            with open("/config.json", "w") as f:
                ujson.dump(cfg, f)
        except Exception:
            pass
        print("config updated to rev", rev)

    def load_cached_config(self):
        """开机先读上次落盘的配置，没网也能按正确阈值工作。"""
        try:
            with open("/config.json") as f:
                self.config = ujson.load(f)
                self.config_rev = self.config.get("rev", -1)
        except Exception:
            self.config = {}
        return self.config
