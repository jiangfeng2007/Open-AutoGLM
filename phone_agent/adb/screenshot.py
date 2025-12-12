#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Android 截屏工具（带设备号）
支持单设备/多设备，失败自动返回黑屏并标记原因。
"""

from __future__ import annotations

import base64
import os
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from io import BytesIO
from typing import List, Optional

from PIL import Image


# ---------- 数据模型 ----------
@dataclass
class Screenshot:
    base64_data: str
    width: int
    height: int
    device_id: str
    is_sensitive: bool = False


# ---------- 内部工具 ----------
def _run(cmd: List[str], timeout: int = 10) -> str:
    """执行命令并返回 stdout，非零退出码抛 RuntimeError。"""
    cp = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if cp.returncode != 0:
        raise RuntimeError(f"命令失败: {' '.join(cmd)}\n{cp.stderr}")
    return cp.stdout


def _get_single_device() -> str:
    """返回当前唯一在线设备序列号；非唯一则抛异常。"""
    out = _run(["adb", "devices"]).strip().splitlines()
    devices = [ln.split("\t")[0] for ln in out if ln.endswith("\tdevice")]
    if len(devices) != 1:
        raise RuntimeError(f"当前连接设备数={len(devices)}，必须显式指定 device_id")
    return devices[0]


def _build_adb_prefix(device_id: Optional[str]) -> List[str]:
    """构造 adb -s 前缀，并返回最终使用的 device_id。"""
    real_id = device_id or _get_single_device()
    return ["adb", "-s", real_id], real_id


def _black_fallback(device_id: str, is_sensitive: bool) -> Screenshot:
    """生成黑屏 fallback。"""
    w, h = 1080, 2400
    img = Image.new("RGB", (w, h), color="black")
    buf = BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return Screenshot(
        base64_data=b64, width=w, height=h, device_id=device_id, is_sensitive=is_sensitive
    )


# ---------- 主入口 ----------
def get_screenshot(device_id: Optional[str] = None, timeout: int = 10) -> Screenshot:
    """
    截屏并返回 Screenshot 对象，始终携带实际使用的 device_id。
    失败时返回黑屏，is_sensitive=True 表示因敏感界面被系统拒绝。
    """
    try:
        adb_prefix, real_id = _build_adb_prefix(device_id)
        remote = "/sdcard/tmp_screenshot.png"
        local = os.path.join(tempfile.gettempdir(), f"scr_{uuid.uuid4().hex}.png")

        # 1. 截屏
        out = _run(adb_prefix + ["shell", "screencap", "-p", remote], timeout=timeout)
        if "Status: -1" in out or "Failed" in out:
            return _black_fallback(real_id, is_sensitive=True)

        # 2. pull
        _run(adb_prefix + ["pull", remote, local], timeout=30)

        # 3. 编码
        with Image.open(local) as img:
            w, h = img.size
            buf = BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode()

        # 4. 清理
        os.remove(local)
        _run(adb_prefix + ["shell", "rm", "-f", remote], timeout=5)

        return Screenshot(
            base64_data=b64,
            width=w,
            height=h,
            device_id=real_id,
            is_sensitive=False,
        )

    except Exception as exc:
        # 任何异常都返回黑屏，device_id 仍带回
        print(f"[Screenshot] {exc}")
        return _black_fallback(
            device_id=real_id if "real_id" in locals() else (device_id or "unknown"),
            is_sensitive=False,
        )


# ---------- CLI 简单测试 ----------
if __name__ == "__main__":
    import json

    pic = get_screenshot()
    print(json.dumps({"device_id": pic.device_id, "size": [pic.width, pic.height],
                      "is_sensitive": pic.is_sensitive, "base64_len": len(pic.base64_data)},
                     ensure_ascii=False, indent=2))
