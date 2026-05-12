"""
51AirClass 性能测试自动化脚本
流程：OCR识别"开始测试"按钮 → 点击 → 轮询等待"测试完成" → 截图保存
"""

import time
import os
import pyautogui
import easyocr
import numpy as np
from PIL import Image
from datetime import datetime

# ── 配置 ──────────────────────────────────────────────────
SAVE_DIR = r"D:\ACAuto\results"
POLL_INTERVAL = 3          # 轮询间隔（秒）
TIMEOUT = 600              # 最大等待时长（秒，10分钟）
CONFIDENCE = 0.6           # OCR文字匹配置信度阈值
# ──────────────────────────────────────────────────────────

# 初始化 EasyOCR（中英文）
print("正在初始化 OCR 引擎...")
reader = easyocr.Reader(['ch_sim', 'en'], gpu=False)
print("OCR 引擎就绪")

os.makedirs(SAVE_DIR, exist_ok=True)


def capture_screen() -> np.ndarray:
    """截取全屏并转为 numpy 数组"""
    screenshot = pyautogui.screenshot()
    return np.array(screenshot)


def ocr_screen(img: np.ndarray):
    """对屏幕图像做 OCR，返回识别结果列表"""
    return reader.readtext(img)


def find_text_center(results, target_text: str):
    """
    在 OCR 结果中查找目标文字，返回其中心坐标 (x, y)。
    未找到返回 None。
    """
    for (bbox, text, conf) in results:
        if target_text in text and conf >= CONFIDENCE:
            # bbox 格式：[[x1,y1],[x2,y1],[x2,y2],[x1,y2]]
            xs = [p[0] for p in bbox]
            ys = [p[1] for p in bbox]
            cx = int(sum(xs) / len(xs))
            cy = int(sum(ys) / len(ys))
            print(f"  找到文字「{text}」置信度={conf:.2f} 中心=({cx},{cy})")
            return cx, cy
    return None


def has_text(results, target_text: str) -> bool:
    """检查 OCR 结果中是否存在目标文字"""
    for (_, text, conf) in results:
        if target_text in text and conf >= CONFIDENCE:
            return True
    return False


def save_screenshot(img: np.ndarray) -> str:
    """以当前时间为文件名保存截图，返回保存路径"""
    filename = datetime.now().strftime("%Y%m%d_%H%M%S") + ".png"
    save_path = os.path.join(SAVE_DIR, filename)
    Image.fromarray(img).save(save_path)
    return save_path


def main():
    # ── 第一步：找"开始测试"按钮并点击 ──────────────────────
    print("\n[Step 1] 正在扫描屏幕，查找「开始测试」按钮...")
    img = capture_screen()
    results = ocr_screen(img)

    pos = find_text_center(results, "开始测试")
    if pos is None:
        print("未找到「开始测试」按钮，请确认已打开性能测试页面后重试。")
        return

    print(f"[Step 1] 找到按钮，点击坐标 {pos}")
    pyautogui.click(pos[0], pos[1])
    time.sleep(1)  # 等待按钮状态切换

    # ── 第二步：确认已切换为"停止测试"，表明测试已开始 ────────
    print("\n[Step 2] 验证测试已启动（等待「停止测试」出现）...")
    img = capture_screen()
    results = ocr_screen(img)
    if has_text(results, "停止测试"):
        print("[Step 2] 确认：测试已启动")
    else:
        print("[Step 2] 警告：未检测到「停止测试」，测试可能未正常启动，继续等待...")

    # ── 第三步：轮询等待"测试完成" ────────────────────────────
    print(f"\n[Step 3] 轮询等待「测试完成」（最长等待 {TIMEOUT} 秒）...")
    start_time = time.time()

    while True:
        elapsed = time.time() - start_time
        if elapsed > TIMEOUT:
            print(f"[Step 3] 超时（{TIMEOUT}秒），未检测到「测试完成」，退出。")
            return

        time.sleep(POLL_INTERVAL)
        img = capture_screen()
        results = ocr_screen(img)

        if has_text(results, "测试完成"):
            print(f"[Step 3] 检测到「测试完成」（耗时 {elapsed:.0f} 秒）")
            break

        print(f"  [{elapsed:.0f}s] 测试进行中...")

    # ── 第四步：截图保存 ──────────────────────────────────────
    print("\n[Step 4] 正在截图保存...")
    img = capture_screen()
    path = save_screenshot(img)
    print(f"[Step 4] 截图已保存：{path}")
    print("\n全部流程完成！")


if __name__ == "__main__":
    main()
