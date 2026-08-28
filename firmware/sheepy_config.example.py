"""板端上行配置。复制成同目录下的 `sheepy_config.py` 再填值。

sheepy_config.py 已被 gitignore —— 它同时装着 Wi-Fi 密码和 API_TOKEN。
"""

# Wi-Fi：现场换网就改这两行。ESP32-S3 只支持 2.4GHz。
WIFI_SSID = "你的 Wi-Fi 名称"
WIFI_PASSWORD = "你的 Wi-Fi 密码"

# Cloudflare Worker。走 workers.dev 在国内会被 DNS 污染，必须用自有域名。
BASE_URL = "https://sheepy.timoz.me"
API_TOKEN = "Worker 的 API_TOKEN，和 wrangler secret put 设的一致"

# 和 apps/ios/Sources/Backend.swift 的 childID 是同一个值。
# 两边不一致的话，App 读到的会是一个空的孩子。
CHILD_ID = "sheepy"
DEVICE_ID = "esp32-s3-01"

# 攒够多少秒发一批。TLS 握手比传输本身贵得多，不值得一分钟一次。
BATCH_SECONDS = 60
