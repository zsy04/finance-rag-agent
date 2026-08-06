"""等待前端 vite (5173) 就绪，供 start.bat Step 4 调用。

背景：vite v8 在 Windows 只监听 IPv6 [::1]:5173（不绑 127.0.0.1），
而 .NET TcpClient 在此机器上连 IPv6 loopback 不稳定，故改用 Python
socket 显式探测双地址（Python 连接 ::1 已验证可行）。

返回码：0 = 前端就绪，1 = 60s 超时。
"""

import socket
import sys
import time

PORT = 5173
TIMEOUT = 60
TARGETS = ("::1", "127.0.0.1")  # vite v8 绑 ::1；老版本 / --host 绑 127.0.0.1


def _probe() -> bool:
    for addr in TARGETS:
        try:
            s = socket.create_connection((addr, PORT), timeout=1)
            s.close()
            print(f"Frontend detected on {addr}")
            return True
        except OSError:
            continue
    return False


def main() -> int:
    deadline = time.time() + TIMEOUT
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        if _probe():
            print("READY")
            return 0
        if attempt % 3 == 0:
            print(f"Waiting for frontend... (attempt {attempt})", flush=True)
        time.sleep(1)
    print("NOT_READY")
    return 1


if __name__ == "__main__":
    sys.exit(main())
