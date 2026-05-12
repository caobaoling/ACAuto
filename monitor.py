"""
系统性能监控脚本
每隔 5 秒采集一次：全局 CPU/内存/GPU + 指定进程占用
持续运行 60 秒，结束后输出汇总表格
目标进程关键词：51TalkStudyCenter、ManyCam Virtual Webcam
"""

import time
import csv
import os
import psutil
import GPUtil
from datetime import datetime
from collections import defaultdict

SAVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")

# ── 配置 ──────────────────────────────────────────────────
DURATION       = 60    # 总采集时长（秒）
INTERVAL       = 1     # 采集间隔（秒）
TARGET_NAMES   = ["ACTalk", "ManyCam"]  # 进程名关键词（模糊匹配）
# 注：任务管理器显示"51TalkStudyCenter"，实际进程文件名为 ACTalk.exe
# ──────────────────────────────────────────────────────────

COL_W = {
    "time":    10,
    "cpu":      8,
    "mem":      8,
    "gpu_use":  8,
    "gpu_mem":  9,
    "proc":    30,
    "p_cpu":    9,
    "p_mem":    9,
}

HEADER = (
    f"{'时间':^{COL_W['time']}} | "
    f"{'全局CPU%':^{COL_W['cpu']}} | "
    f"{'全局内存MB':^{COL_W['mem']}} | "
    f"{'GPU使用%':^{COL_W['gpu_use']}} | "
    f"{'GPU内存%':^{COL_W['gpu_mem']}} | "
    f"{'进程名':^{COL_W['proc']}} | "
    f"{'进程CPU%':^{COL_W['p_cpu']}} | "
    f"{'进程内存MB':^{COL_W['p_mem']}}"
)
SEP = "-" * len(HEADER)


def get_gpu():
    """返回 (gpu_load%, gpu_mem%) 如无GPU返回 (None, None)"""
    try:
        gpus = GPUtil.getGPUs()
        if gpus:
            g = gpus[0]
            return round(g.load * 100, 1), round(g.memoryUtil * 100, 1)
    except Exception:
        pass
    return None, None


def find_target_procs():
    """
    扫描进程列表，返回匹配目标关键词的 {keyword: [proc, ...]} 字典。
    用于初始化持久进程对象，调用后需预热 cpu_percent。
    """
    found = {kw: [] for kw in TARGET_NAMES}
    for proc in psutil.process_iter(['name']):
        try:
            name = proc.info['name'] or ""
            for keyword in TARGET_NAMES:
                if keyword.lower() in name.lower():
                    found[keyword].append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return found


def get_target_procs(tracked: dict):
    """
    从持久进程对象中采集 CPU%/内存，返回 list of (display_name, cpu%, mem_mb)。
    tracked: {keyword: [proc, ...]}
    """
    matched = {}

    for keyword, procs in tracked.items():
        for proc in procs:
            try:
                cpu = round(proc.cpu_percent(interval=None) or 0.0, 1)
                mem = round(proc.memory_info().rss / 1024 / 1024, 1)
                name = proc.name()
                if keyword not in matched:
                    matched[keyword] = [0.0, 0.0, 0, name]
                matched[keyword][0] += cpu
                matched[keyword][1] += mem
                matched[keyword][2] += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    result = []
    for keyword, (cpu_sum, mem_sum, count, raw_name) in matched.items():
        display = raw_name if count == 1 else f"{keyword}(*{count})"
        result.append((display, round(cpu_sum, 1), round(mem_sum, 1)))

    # 51TalkStudyCenter 未找到时显示提示行；ManyCam 未找到则静默跳过
    found_keywords = set(matched.keys())
    for keyword in TARGET_NAMES:
        if keyword not in found_keywords:
            if keyword != "ManyCam":
                result.append(("51TalkStudyCenter (ACTalk) [未运行]", "N/A", "N/A"))

    return result


def fmt_row(ts, cpu, mem, gpu_use, gpu_mem, proc, p_cpu, p_mem):
    gpu_use_s = f"{gpu_use}" if gpu_use is not None else "N/A"
    gpu_mem_s = f"{gpu_mem}" if gpu_mem is not None else "N/A"
    return (
        f"{ts:^{COL_W['time']}} | "
        f"{str(cpu):^{COL_W['cpu']}} | "
        f"{str(mem):^{COL_W['mem']}} | "
        f"{gpu_use_s:^{COL_W['gpu_use']}} | "
        f"{gpu_mem_s:^{COL_W['gpu_mem']}} | "
        f"{proc:<{COL_W['proc']}} | "
        f"{str(p_cpu):^{COL_W['p_cpu']}} | "
        f"{str(p_mem):^{COL_W['p_mem']}}"
    )


def main():
    cpu_logical  = psutil.cpu_count(logical=True)
    cpu_physical = psutil.cpu_count(logical=False)
    print(f"\n开始监控，持续 {DURATION} 秒，每 {INTERVAL} 秒采样一次")
    print(f"CPU：{cpu_physical} 物理核心 / {cpu_logical} 逻辑核心")
    print(f"目标进程：{TARGET_NAMES}\n")
    print(SEP)
    print(HEADER)
    print(SEP)

    # 扫描目标进程，预热 cpu_percent（首次调用返回0，需丢弃）
    tracked = find_target_procs()
    psutil.cpu_percent(interval=None)
    for procs in tracked.values():
        for proc in procs:
            try:
                proc.cpu_percent(interval=None)
            except Exception:
                pass
    time.sleep(1)

    # 准备 CSV 文件
    os.makedirs(SAVE_DIR, exist_ok=True)
    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_detail_path  = os.path.join(SAVE_DIR, f"monitor_{run_ts}_detail.csv")
    csv_summary_path = os.path.join(SAVE_DIR, f"monitor_{run_ts}_summary.csv")

    detail_rows = []   # 明细数据（每次采样）

    # 用于汇总统计
    summary = defaultdict(lambda: {"cpu": [], "mem": [], "gpu_use": [], "gpu_mem": []})

    start = time.time()
    while time.time() - start < DURATION:
        ts        = datetime.now().strftime("%H:%M:%S")
        cpu_total = psutil.cpu_percent(interval=None)
        mem_total = round(psutil.virtual_memory().used / 1024 / 1024)
        gpu_use, gpu_mem = get_gpu()
        procs     = get_target_procs(tracked)

        # 记录全局汇总
        summary["__global__"]["cpu"].append(cpu_total)
        summary["__global__"]["mem"].append(mem_total)
        if gpu_use is not None:
            summary["__global__"]["gpu_use"].append(gpu_use)
            summary["__global__"]["gpu_mem"].append(gpu_mem)

        # 打印每个目标进程一行，同步写入明细数据
        first = True
        for (proc_name, p_cpu, p_mem) in procs:
            if first:
                row = fmt_row(ts, cpu_total, mem_total, gpu_use, gpu_mem, proc_name, p_cpu, p_mem)
                first = False
            else:
                row = fmt_row("", "", "", "", "", proc_name, p_cpu, p_mem)
            print(row)

            # 记录明细行（CSV）
            detail_rows.append({
                "时间":      ts,
                "全局CPU%":  cpu_total,
                "全局内存%": mem_total,
                "GPU使用%":  gpu_use if gpu_use is not None else "",
                "GPU内存%":  gpu_mem if gpu_mem is not None else "",
                "进程名":    proc_name,
                "进程CPU%":  p_cpu,
                "进程内存MB": p_mem,
            })

            # 记录进程汇总
            if p_cpu != "N/A":
                summary[proc_name]["cpu"].append(p_cpu)
                summary[proc_name]["mem"].append(p_mem)

        print(SEP)
        time.sleep(INTERVAL)

    # ── 汇总统计 ──────────────────────────────────────────
    print("\n\n========== 汇总统计（均值 / 峰值）==========\n")

    def avg(lst):
        return round(sum(lst) / len(lst), 1) if lst else "N/A"
    def peak(lst):
        return max(lst) if lst else "N/A"

    g = summary["__global__"]
    print(f"  全局 CPU     均值={avg(g['cpu'])}%  峰值={peak(g['cpu'])}%")
    print(f"  全局 内存    均值={avg(g['mem'])}MB  峰值={peak(g['mem'])}MB")
    if g["gpu_use"]:
        print(f"  GPU  使用率  均值={avg(g['gpu_use'])}%  峰值={peak(g['gpu_use'])}%")
        print(f"  GPU  显存    均值={avg(g['gpu_mem'])}%  峰值={peak(g['gpu_mem'])}%")
    else:
        print("  GPU          未检测到 GPU 或无法读取")

    print()
    for name, data in summary.items():
        if name == "__global__":
            continue
        print(f"  [{name}]")
        print(f"    CPU  均值={avg(data['cpu'])}%  峰值={peak(data['cpu'])}%")
        print(f"    内存 均值={avg(data['mem'])}MB 峰值={peak(data['mem'])}MB")

    # ── 保存明细 CSV ──────────────────────────────────────────
    fieldnames = ["时间", "全局CPU%", "全局内存%", "GPU使用%", "GPU内存%", "进程名", "进程CPU%", "进程内存MB"]
    with open(csv_detail_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(detail_rows)

    # ── 保存汇总 CSV ──────────────────────────────────────────
    summary_rows = []
    g = summary["__global__"]
    summary_rows.append({"指标": "全局CPU%",  "均值": avg(g["cpu"]),     "峰值": peak(g["cpu"])})
    summary_rows.append({"指标": "全局内存%", "均值": avg(g["mem"]),     "峰值": peak(g["mem"])})
    summary_rows.append({"指标": "GPU使用%",  "均值": avg(g["gpu_use"]), "峰值": peak(g["gpu_use"])})
    summary_rows.append({"指标": "GPU内存%",  "均值": avg(g["gpu_mem"]), "峰值": peak(g["gpu_mem"])})
    for name, data in summary.items():
        if name == "__global__":
            continue
        summary_rows.append({"指标": f"{name} CPU%",  "均值": avg(data["cpu"]), "峰值": peak(data["cpu"])})
        summary_rows.append({"指标": f"{name} 内存MB", "均值": avg(data["mem"]), "峰值": peak(data["mem"])})

    with open(csv_summary_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["指标", "均值", "峰值"])
        writer.writeheader()
        writer.writerows(summary_rows)

    print(f"\n明细数据：{csv_detail_path}")
    print(f"汇总数据：{csv_summary_path}")
    print("\n监控结束。")


if __name__ == "__main__":
    main()
