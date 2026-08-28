"""Small cooperative HTTPS helpers for direct MiMo access on MicroPython."""

import binascii
import json
import socket
import ssl
import time


_DNS_CACHE = {}


def _would_block(error):
    try:
        code = error.args[0]
    except Exception:
        return False
    return code in (11, 35, 110, 115, 116, 118, 119, 120, 128)


class BytesBody:
    """One-shot request body."""

    def __init__(self, body):
        self.body = body
        self.content_length = len(body)
        self.sent = False

    def next_chunk(self):
        if self.sent:
            return None
        self.sent = True
        return self.body


class AudioBase64Body:
    """Stream a WAV buffer into the Base64 string inside a JSON request."""

    RAW_CHUNK_BYTES = 12_288  # divisible by three

    def __init__(self, audio, prefix, suffix):
        self.audio = audio
        self.prefix = prefix
        self.suffix = suffix
        self.audio_offset = 0
        self.stage = 0
        encoded_length = 4 * ((len(audio) + 2) // 3)
        self.content_length = len(prefix) + encoded_length + len(suffix)

    def next_chunk(self):
        if self.stage == 0:
            self.stage = 1
            return self.prefix
        if self.stage == 1:
            if self.audio_offset < len(self.audio):
                end = min(
                    self.audio_offset + self.RAW_CHUNK_BYTES,
                    len(self.audio),
                )
                raw = bytes(memoryview(self.audio)[self.audio_offset : end])
                self.audio_offset = end
                encoded = binascii.b2a_base64(raw).strip()
                expected = 4 * ((len(raw) + 2) // 3)
                if len(encoded) != expected:
                    raise RuntimeError("Base64 audio chunk length mismatch")
                return encoded
            self.stage = 2
        if self.stage == 2:
            self.stage = 3
            return self.suffix
        return None


class HTTPResponseDecoder:
    """Incrementally decode HTTP/1.1 headers and chunked/content-length bodies."""

    MAX_HEADER_BYTES = 16_384

    def __init__(self, on_body=None, response_limit=65_536):
        self.on_body = on_body
        self.response_limit = int(response_limit)
        self.buffer = bytearray()
        self.body = bytearray()
        self.headers_complete = False
        self.status = None
        self.headers = {}
        self.chunked = False
        self.remaining = None
        self.chunk_remaining = None
        self.reading_trailers = False
        self.complete = False

    def _deliver(self, data):
        if not data:
            return
        if self.status is not None and 200 <= self.status < 300 and self.on_body:
            self.on_body(data)
            return
        if len(self.body) + len(data) > self.response_limit:
            raise RuntimeError("MiMo HTTP response is too large")
        self.body.extend(data)

    def _parse_headers(self):
        marker = self.buffer.find(b"\r\n\r\n")
        if marker < 0:
            if len(self.buffer) > self.MAX_HEADER_BYTES:
                raise RuntimeError("MiMo HTTP headers are too large")
            return False
        encoded = bytes(self.buffer[:marker])
        self.buffer = self.buffer[marker + 4 :]
        lines = encoded.split(b"\r\n")
        status_parts = lines[0].split()
        if len(status_parts) < 2:
            raise RuntimeError("MiMo HTTP status line is invalid")
        self.status = int(status_parts[1])
        headers = {}
        for line in lines[1:]:
            if b":" not in line:
                continue
            name, value = line.split(b":", 1)
            headers[name.decode().strip().lower()] = value.decode().strip()
        self.headers = headers
        transfer = headers.get("transfer-encoding", "").lower()
        self.chunked = "chunked" in transfer
        if not self.chunked and "content-length" in headers:
            self.remaining = int(headers["content-length"])
            if self.remaining == 0:
                self.complete = True
        self.headers_complete = True
        return True

    def _drain_chunked(self):
        while not self.complete:
            if self.reading_trailers:
                if self.buffer.startswith(b"\r\n"):
                    self.buffer = self.buffer[2:]
                    self.complete = True
                    return
                marker = self.buffer.find(b"\r\n\r\n")
                if marker < 0:
                    return
                self.buffer = self.buffer[marker + 4 :]
                self.complete = True
                return
            if self.chunk_remaining is None:
                marker = self.buffer.find(b"\r\n")
                if marker < 0:
                    return
                size_text = bytes(self.buffer[:marker]).split(b";", 1)[0]
                self.buffer = self.buffer[marker + 2 :]
                self.chunk_remaining = int(size_text, 16)
                if self.chunk_remaining == 0:
                    self.chunk_remaining = None
                    self.reading_trailers = True
                    continue
            needed = self.chunk_remaining + 2
            if len(self.buffer) < needed:
                return
            payload = bytes(self.buffer[: self.chunk_remaining])
            if self.buffer[self.chunk_remaining : needed] != b"\r\n":
                raise RuntimeError("MiMo HTTP chunk terminator is invalid")
            self.buffer = self.buffer[needed:]
            self.chunk_remaining = None
            self._deliver(payload)

    def _drain_plain(self):
        if self.remaining is None:
            if self.buffer:
                payload = bytes(self.buffer)
                self.buffer = bytearray()
                self._deliver(payload)
            return
        if self.remaining <= 0:
            self.complete = True
            return
        count = min(self.remaining, len(self.buffer))
        if count:
            payload = bytes(self.buffer[:count])
            self.buffer = self.buffer[count:]
            self.remaining -= count
            self._deliver(payload)
        if self.remaining == 0:
            self.complete = True

    def feed(self, data):
        if self.complete or not data:
            return
        self.buffer.extend(data)
        if not self.headers_complete and not self._parse_headers():
            return
        if self.complete:
            return
        if self.chunked:
            self._drain_chunked()
        else:
            self._drain_plain()

    def finish_eof(self):
        if not self.headers_complete:
            raise RuntimeError("MiMo closed before HTTP headers")
        if self.chunked and not self.complete:
            raise RuntimeError("MiMo closed during chunked response")
        if self.remaining not in (None, 0):
            raise RuntimeError("MiMo closed before complete response")
        if self.remaining is None and self.buffer:
            self._drain_plain()
        self.complete = True


class HTTPSRequest:
    """Cooperative HTTPS POST transaction with a streaming body source."""

    def __init__(
        self,
        host,
        port,
        path,
        api_key,
        body_source,
        accept="application/json",
        on_body=None,
        response_limit=65_536,
        timeout_ms=90_000,
        ca_path=None,
    ):
        self.host = host
        self.port = int(port)
        self.path = path
        self.api_key = api_key
        self.body_source = body_source
        self.accept = accept
        self.timeout_ms = int(timeout_ms)
        self.ca_path = ca_path
        self.response = HTTPResponseDecoder(on_body, response_limit)
        self.socket = None
        self.tx_buffer = None
        self.tx_offset = 0
        self.body_finished = False
        self.last_progress_at = time.ticks_ms()
        self.open_attempts = 0
        self.next_open_at = self.last_progress_at

    @property
    def complete(self):
        return self.response.complete

    def _open(self):
        address = _DNS_CACHE.get((self.host, self.port))
        if address is None:
            address = socket.getaddrinfo(self.host, self.port)[0][-1]
            _DNS_CACHE[(self.host, self.port)] = address
        raw = socket.socket()
        try:
            # Certificate validation adds an extra round trip and parsing work
            # on ESP32.  Keep the blocking handshake below the main watchdog
            # window in normal conditions while tolerating hotspot jitter.
            raw.settimeout(7)
            try:
                raw.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except Exception:
                pass
            raw.connect(address)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            if self.ca_path:
                context.verify_mode = ssl.CERT_REQUIRED
                ca_file = open(self.ca_path, "rb")
                try:
                    ca_data = ca_file.read()
                finally:
                    ca_file.close()
                context.load_verify_locations(cadata=ca_data)
            wrapped = context.wrap_socket(raw, server_hostname=self.host)
            wrapped.setblocking(False)
        except Exception:
            try:
                raw.close()
            except Exception:
                pass
            raise
        self.socket = wrapped
        header = (
            "POST %s HTTP/1.1\r\n"
            "Host: %s\r\n"
            "Authorization: Bearer %s\r\n"
            "Content-Type: application/json\r\n"
            "Accept: %s\r\n"
            "User-Agent: desk-study-companion-mimo/1.0\r\n"
            "Connection: close\r\n"
            "Content-Length: %d\r\n\r\n"
            % (
                self.path,
                self.host,
                self.api_key,
                self.accept,
                self.body_source.content_length,
            )
        ).encode()
        self.tx_buffer = header
        self.tx_offset = 0
        self.last_progress_at = time.ticks_ms()

    def _send(self):
        if self.tx_buffer is None:
            return False
        try:
            sent = self.socket.write(
                memoryview(self.tx_buffer)[self.tx_offset :]
            )
        except OSError as exc:
            if _would_block(exc):
                return False
            raise
        # MicroPython's non-blocking SSL stream returns None when it cannot
        # accept data yet.  Treating that as a successful full write silently
        # dropped request bodies, leaving MiMo waiting for Content-Length.
        if sent is None:
            return False
        if sent <= 0:
            raise RuntimeError("MiMo HTTPS send made no progress")
        self.tx_offset += sent
        self.last_progress_at = time.ticks_ms()
        if self.tx_offset >= len(self.tx_buffer):
            self.tx_buffer = None
            self.tx_offset = 0
        return True

    def _receive(self):
        try:
            data = self.socket.read(8_192)
        except OSError as exc:
            if _would_block(exc):
                return False
            raise
        if data is None:
            return False
        if data == b"":
            self.response.finish_eof()
            self.close()
            return True
        self.response.feed(data)
        self.last_progress_at = time.ticks_ms()
        if self.response.complete:
            self.close()
        return True

    def step(self, now_ms=None):
        if self.complete:
            return True
        current = time.ticks_ms() if now_ms is None else now_ms
        if self.socket is None:
            if time.ticks_diff(current, self.next_open_at) < 0:
                return False
            try:
                self._open()
            except OSError:
                self.open_attempts += 1
                if self.open_attempts >= 8:
                    raise
                self.next_open_at = time.ticks_add(current, 750)
            return False
        if time.ticks_diff(current, self.last_progress_at) >= self.timeout_ms:
            raise RuntimeError("MiMo HTTPS request timed out")
        if self.tx_buffer is not None:
            self._send()
            return False
        if not self.body_finished:
            chunk = self.body_source.next_chunk()
            if chunk is not None:
                self.tx_buffer = chunk
                self.tx_offset = 0
                self._send()
                return False
            self.body_finished = True
        self._receive()
        return self.complete

    def ensure_success(self):
        status = self.response.status
        if status is None:
            raise RuntimeError("MiMo HTTP response has no status")
        if status < 200 or status >= 300:
            detail = bytes(self.response.body[:256]).decode("utf-8", "replace")
            raise RuntimeError("MiMo HTTP %d: %s" % (status, detail))

    def close(self):
        if self.socket is not None:
            try:
                self.socket.close()
            except Exception:
                pass
        self.socket = None


class SSEAudioDecoder:
    """Extract Base64 PCM blocks from MiMo's OpenAI-compatible SSE stream."""

    MAX_LINE_BYTES = 262_144

    def __init__(self, on_audio, max_pcm_bytes):
        self.on_audio = on_audio
        self.max_pcm_bytes = int(max_pcm_bytes)
        self.buffer = bytearray()
        self.pcm_bytes = 0
        self.done = False

    def _line(self, line):
        line = line.strip()
        if not line.startswith(b"data:"):
            return
        payload = line[5:].strip()
        if not payload:
            return
        if payload == b"[DONE]":
            self.done = True
            return
        event = json.loads(payload.decode())
        choices = event.get("choices") or []
        if not choices:
            return
        delta = choices[0].get("delta") or {}
        audio = delta.get("audio") if isinstance(delta, dict) else None
        if not isinstance(audio, dict) or not audio.get("data"):
            return
        pcm = binascii.a2b_base64(audio["data"])
        if self.pcm_bytes + len(pcm) > self.max_pcm_bytes:
            raise RuntimeError("MiMo TTS answer exceeds playback buffer")
        self.pcm_bytes += len(pcm)
        self.on_audio(pcm)

    def feed(self, data):
        self.buffer.extend(data)
        if len(self.buffer) > self.MAX_LINE_BYTES:
            raise RuntimeError("MiMo SSE line is too large")
        while True:
            marker = self.buffer.find(b"\n")
            if marker < 0:
                return
            line = bytes(self.buffer[:marker])
            self.buffer = self.buffer[marker + 1 :]
            self._line(line)

    def finish(self):
        if self.buffer.strip():
            self._line(bytes(self.buffer))
        self.buffer = bytearray()


def extract_message(body):
    document = json.loads(bytes(body).decode())
    if isinstance(document.get("error"), dict):
        raise RuntimeError(document["error"].get("message", "MiMo API error"))
    choices = document.get("choices") or []
    if not choices:
        raise RuntimeError("MiMo response contains no choices")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("MiMo response contains no text")
    return " ".join(content.split()).strip()


def extract_spoken_answer(content, limit=60):
    text = content.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline >= 0:
            text = text[first_newline + 1 :]
        if text.endswith("```"):
            text = text[:-3].rstrip()
    try:
        answer = json.loads(text)
    except Exception:
        answer = None
    if isinstance(answer, dict):
        spoken = answer.get("spoken_answer") or answer.get("short_answer")
        if spoken:
            text = str(spoken)
    text = " ".join(text.split()).strip()
    if not text:
        raise RuntimeError("MiMo solver returned an empty answer")
    if len(text) <= limit:
        return text
    candidate = text[:limit]
    cut = max(candidate.rfind(mark) for mark in "。！？；")
    if cut >= max(16, limit // 2):
        return candidate[: cut + 1]
    return candidate[: limit - 1].rstrip("，,；;：:。.!！?") + "。"
