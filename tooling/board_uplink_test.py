#!/usr/bin/env python3
"""板端上行自检：连 Wi-Fi → DNS → TLS → POST /ingest → 打印 Worker 回的配置。

这条链路上板子这一段最容易出问题（TLS 内存、DNS、Cloudflare 的 UA 拦截），
所以单独拎出来测，不跟主程序混在一起。

  python3 tooling/board_uplink_test.py                 # 用板上 sheepy_config 的 Wi-Fi
  python3 tooling/board_uplink_test.py --ssid X --pass Y
"""
import argparse, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tooling"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ssid")
    ap.add_argument("--password", "--pass", dest="password")
    ap.add_argument("--port", default="/dev/cu.usbserial-210")
    a = ap.parse_args()

    scratch = os.environ.get("SHEEPY_BOARD_HELPER")
    if scratch:
        sys.path.insert(0, scratch)
    from board import Board

    creds = ""
    if a.ssid:
        creds = "SSID, PW = %r, %r" % (a.ssid, a.password or "")
    code = """__CREDS__
import network, time, ujson, gc
import sheepy_config as c
import net as netmod
try:
    SSID
except NameError:
    SSID, PW = c.WIFI_SSID, c.WIFI_PASSWORD

w = network.WLAN(network.STA_IF); w.active(True)
if not w.isconnected():
    w.connect(SSID, PW)
    for _ in range(60):
        if w.isconnected(): break
        time.sleep(0.5)
print("1 wifi     :", w.isconnected(), w.ifconfig()[0] if w.isconnected() else "-")
if not w.isconnected():
    raise SystemExit

import socket
ai = socket.getaddrinfo("sheepy.timoz.me", 443)
print("2 dns      :", ai[0][-1])

# 先对时。样本的 ts 是 UTC，RTC 不准就全废了。
import ntptime, machine
try:
    ntptime.settime()
    sh = time.localtime(time.time() + 8 * 3600)
    machine.RTC().datetime((sh[0],sh[1],sh[2],sh[6],sh[3],sh[4],sh[5],0))
    print("3 ntp      : 北京", "%04d-%02d-%02d %02d:%02d:%02d" % sh[:6])
except Exception as e:
    print("3 ntp      : FAILED", e)

gc.collect()
print("4 freemem  :", gc.mem_free())

n = netmod.Net(SSID, PW, c.BASE_URL, c.DEVICE_ID, c.CHILD_ID,
               token=c.API_TOKEN)
n.online = True
n.hp, n.grow, n.form = 91, 55, "normal"
ts = netmod.utc_stamp()
ok = n._post([{"ts": ts, "present": True, "distance_mm": 512,
               "light_left": 3880, "light_right": 3820,
               "temperature": 26.0, "humidity": 55,
               "pir_hits": 6, "abnormal": False}])
print("5 post     :", ok, "ts(UTC)=" + ts)
print("6 config   :", ujson.dumps(n.config))
""".replace("__CREDS__", creds)

    b = Board(a.port)
    try:
        out, err = b.exec(code, timeout=120)
        print(out, end="")
        if err.strip():
            print("\n[板端异常]\n" + err, file=sys.stderr)
    finally:
        b.close()


if __name__ == "__main__":
    main()
