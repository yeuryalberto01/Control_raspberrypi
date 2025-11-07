"""
System metrics collection utilities, supporting both local (psutil) and remote (SSH) hosts.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from typing import AsyncGenerator, Dict, List, Optional, Tuple

import psutil
from fabric import Connection

from .schemas import Metrics, ProcessMetric
from .system_ops import get_uptime_seconds


def _read_temperature() -> Optional[float]:
    try:
        temps = psutil.sensors_temperatures()
    except (AttributeError, NotImplementedError):
        return None

    if not temps:
        return None

    # Prefer common Raspberry Pi labels.
    for key in ("cpu-thermal", "soc_thermal", "gpu"):
        entries = temps.get(key)
        if entries:
            return round(entries[0].current, 2)

    # Fallback to the first available sensor.
    for entries in temps.values():
        if entries:
            return round(entries[0].current, 2)
    return None


@dataclass
class _NetSnapshot:
    timestamp: float
    rx_bytes: int
    tx_bytes: int


_LOCAL_NET_SNAPSHOT: Optional[_NetSnapshot] = None
_PROCESS_SAMPLE_INTERVAL = 0.15


def _bytes_to_mb(value: int) -> int:
    return int(value / (1024**2))


def _bytes_to_gb(value: int) -> float:
    return round(value / (1024**3), 2)


def _gather_net_totals(counters: Dict[str, psutil._common.snetio]) -> Tuple[int, int]:
    rx = tx = 0
    for name, stats in counters.items():
        if name.lower().startswith("lo"):
            continue
        rx += stats.bytes_recv
        tx += stats.bytes_sent
    return rx, tx


def _read_local_network_rates() -> Tuple[float, float]:
    global _LOCAL_NET_SNAPSHOT
    timestamp = time.monotonic()
    counters = psutil.net_io_counters(pernic=True)
    rx_bytes, tx_bytes = _gather_net_totals(counters)

    snapshot = _LOCAL_NET_SNAPSHOT
    _LOCAL_NET_SNAPSHOT = _NetSnapshot(timestamp, rx_bytes, tx_bytes)

    if not snapshot or timestamp <= snapshot.timestamp:
        return 0.0, 0.0

    delta = timestamp - snapshot.timestamp
    if delta <= 0:
        return 0.0, 0.0

    rx_kbps = ((rx_bytes - snapshot.rx_bytes) / 1024) / delta
    tx_kbps = ((tx_bytes - snapshot.tx_bytes) / 1024) / delta
    return max(rx_kbps, 0.0), max(tx_kbps, 0.0)


def _collect_top_processes_local(limit: int = 5) -> Tuple[List[ProcessMetric], List[ProcessMetric]]:
    processes: Dict[int, Dict[str, object]] = {}
    for proc in psutil.process_iter(attrs=["pid", "name", "memory_percent"]):
        try:
            proc.cpu_percent(interval=None)
            processes[proc.pid] = {
                "proc": proc,
                "name": proc.info.get("name") or "unknown",
                "mem": proc.info.get("memory_percent") or 0.0,
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if processes:
        time.sleep(_PROCESS_SAMPLE_INTERVAL)

    metrics: List[ProcessMetric] = []
    for data in processes.values():
        proc: psutil.Process = data["proc"]  # type: ignore[assignment]
        try:
            cpu = proc.cpu_percent(interval=None)
            mem = float(data["mem"])
            if mem == 0.0:
                mem = proc.memory_percent()
            metrics.append(
                ProcessMetric(
                    pid=proc.pid,
                    name=str(data["name"]),
                    cpu_percent=round(cpu, 2),
                    mem_percent=round(mem, 2),
                )
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    top_cpu = sorted(metrics, key=lambda item: item.cpu_percent, reverse=True)[:limit]
    top_mem = sorted(metrics, key=lambda item: item.mem_percent, reverse=True)[:limit]
    return top_cpu, top_mem


def collect_metrics() -> Metrics:
    """Collects metrics for the LOCAL host using psutil."""
    cpu_per_core = psutil.cpu_percent(interval=None, percpu=True) or []
    cpu_percent = sum(cpu_per_core) / len(cpu_per_core) if cpu_per_core else psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    swap = psutil.swap_memory()
    process_count = len(psutil.pids())
    net_rx_kbps, net_tx_kbps = _read_local_network_rates()
    top_cpu, top_mem = _collect_top_processes_local()

    try:
        load1, load5, load15 = psutil.getloadavg()
    except (AttributeError, OSError):
        load1 = load5 = load15 = 0.0

    return Metrics(
        cpu_percent=round(cpu_percent, 2),
        cpu_cores=len(cpu_per_core) or (psutil.cpu_count(logical=True) or 0),
        cpu_per_core=[round(value, 2) for value in cpu_per_core],
        mem_total_mb=_bytes_to_mb(mem.total),
        mem_used_mb=_bytes_to_mb(mem.used),
        mem_available_mb=_bytes_to_mb(getattr(mem, "available", 0)),
        mem_percent=round(mem.percent, 2),
        swap_total_mb=_bytes_to_mb(swap.total),
        swap_used_mb=_bytes_to_mb(swap.used),
        disk_total_gb=_bytes_to_gb(disk.total),
        disk_used_gb=_bytes_to_gb(disk.used),
        disk_percent=round(disk.percent, 2),
        net_rx_kbps=round(net_rx_kbps, 2),
        net_tx_kbps=round(net_tx_kbps, 2),
        process_count=process_count,
        top_cpu=top_cpu,
        top_mem=top_mem,
        temp_c=_read_temperature(),
        load1=round(load1, 2),
        load5=round(load5, 2),
        load15=round(load15, 2),
        uptime_seconds=get_uptime_seconds(),
    )


def _parse_proc_stat(raw: str) -> Dict[str, List[int]]:
    result: Dict[str, List[int]] = {}
    for line in raw.splitlines():
        if not line.startswith("cpu"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            result[parts[0]] = [int(p) for p in parts[1:]]
        except ValueError:
            continue
    return result


def _cpu_usage_from(samples1: List[int], samples2: List[int]) -> float:
    if not samples1 or not samples2:
        return 0.0
    total1 = sum(samples1)
    total2 = sum(samples2)
    idle1 = samples1[3] if len(samples1) > 3 else 0
    idle2 = samples2[3] if len(samples2) > 3 else 0
    total_delta = total2 - total1
    idle_delta = idle2 - idle1
    if total_delta <= 0:
        return 0.0
    return round(((total_delta - idle_delta) / total_delta) * 100, 2)


def _parse_proc_net_dev(raw: str) -> Tuple[int, int]:
    rx = tx = 0
    for line in raw.splitlines():
        if ":" not in line:
            continue
        iface, data = line.split(":", 1)
        iface = iface.strip()
        if not iface or iface.lower().startswith("lo"):
            continue
        columns = data.split()
        if len(columns) >= 9:
            try:
                rx += int(columns[0])
                tx += int(columns[8])
            except ValueError:
                continue
    return rx, tx


def _parse_ps_table(output: str) -> List[ProcessMetric]:
    entries: List[ProcessMetric] = []
    lines = output.splitlines()
    if not lines:
        return entries
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        try:
            entries.append(
                ProcessMetric(
                    pid=int(parts[0]),
                    name=parts[1],
                    cpu_percent=round(float(parts[2]), 2),
                    mem_percent=round(float(parts[3]), 2),
                )
            )
        except ValueError:
            continue
    return entries


def _collect_top_processes_remote(conn: Connection, limit: int = 5) -> Tuple[List[ProcessMetric], List[ProcessMetric]]:
    cpu_metrics: List[ProcessMetric] = []
    mem_metrics: List[ProcessMetric] = []

    cpu_cmd = conn.run(
        f"ps -eo pid,comm,%cpu,%mem --sort=-%cpu | head -n {limit + 1}",
        hide=True,
        warn=True,
    )
    if cpu_cmd.ok:
        cpu_metrics = _parse_ps_table(cpu_cmd.stdout)[:limit]

    mem_cmd = conn.run(
        f"ps -eo pid,comm,%cpu,%mem --sort=-%mem | head -n {limit + 1}",
        hide=True,
        warn=True,
    )
    if mem_cmd.ok:
        mem_metrics = _parse_ps_table(mem_cmd.stdout)[:limit]

    return cpu_metrics, mem_metrics


def collect_remote_metrics(conn: Connection) -> Metrics:
    """Collects metrics from a REMOTE host via an established Fabric connection."""
    # 1. Get Load Average
    load_result = conn.run("cat /proc/loadavg", hide=True, warn=True)
    load1, load5, load15 = (0.0, 0.0, 0.0)
    if load_result.ok:
        parts = load_result.stdout.split()
        if len(parts) >= 3:
            load1, load5, load15 = float(parts[0]), float(parts[1]), float(parts[2])

    # 2. Get Memory Info (in bytes from `free -b`)
    mem_result = conn.run("free -b", hide=True, warn=True)
    mem_total = mem_used = mem_available = swap_total = swap_used = 0
    mem_percent = 0.0
    if mem_result.ok:
        lines = mem_result.stdout.splitlines()
        if len(lines) > 1:
            parts = lines[1].split()
            if len(parts) >= 7:
                mem_total = int(parts[1])
                mem_used = int(parts[2])
                mem_available = int(parts[6])
                if mem_total > 0:
                    mem_percent = round((mem_used / mem_total) * 100, 2)
        if len(lines) > 2:
            parts = lines[2].split()
            if len(parts) >= 3:
                swap_total = int(parts[1])
                swap_used = int(parts[2])

    # 3. Get Disk Usage for root filesystem
    disk_result = conn.run("df --output=size,used,pcent /", hide=True, warn=True)
    disk_total, disk_used, disk_percent = 0, 0, 0.0
    if disk_result.ok:
        lines = disk_result.stdout.splitlines()
        if len(lines) > 1:
            # Output is like: 1K-blocks      Used Available Use%
            # We get size and used in 1K blocks
            parts = lines[1].split()
            if len(parts) >= 3:
                disk_total = int(parts[0]) * 1024 # to bytes
                disk_used = int(parts[1]) * 1024 # to bytes
                # Parse percentage like '87%'
                pcent_match = re.search(r"(\d+)", parts[2])
                if pcent_match:
                    disk_percent = float(pcent_match.group(1))

    # 4. Get Temperature
    temp_c = None
    temp_result = conn.run("vcgencmd measure_temp", hide=True, warn=True)
    if temp_result.ok:
        match = re.search(r"temp=([\d\.]+)", temp_result.stdout)
        if match:
            temp_c = float(match.group(1))

    # 5. Get Uptime
    uptime_seconds = 0
    uptime_result = conn.run("cat /proc/uptime", hide=True, warn=True)
    if uptime_result.ok:
        uptime_seconds = int(float(uptime_result.stdout.split()[0]))

    # 6. Get CPU Usage (with per-core detail)
    cpu_percent = 0.0
    cpu_per_core: List[float] = []
    stat_result1 = conn.run("cat /proc/stat", hide=True, warn=True)
    cpu_cores = 0
    if stat_result1.ok:
        conn.run("sleep 0.2", hide=True)  # small delay
        stat_result2 = conn.run("cat /proc/stat", hide=True, warn=True)
        if stat_result2.ok:
            stats1 = _parse_proc_stat(stat_result1.stdout)
            stats2 = _parse_proc_stat(stat_result2.stdout)
            if "cpu" in stats1 and "cpu" in stats2:
                cpu_percent = _cpu_usage_from(stats1["cpu"], stats2["cpu"])
            core_names = sorted(name for name in stats1.keys() if name.startswith("cpu") and name != "cpu")
            for name in core_names:
                if name in stats2:
                    cpu_per_core.append(_cpu_usage_from(stats1[name], stats2[name]))
            cpu_per_core = [round(value, 2) for value in cpu_per_core]
            cpu_cores = len(cpu_per_core)
    if cpu_cores == 0:
        nproc_result = conn.run("nproc", hide=True, warn=True)
        if nproc_result.ok:
            try:
                cpu_cores = int(nproc_result.stdout.strip())
            except ValueError:
                cpu_cores = 0

    # 7. Network throughput
    net_rx_kbps = net_tx_kbps = 0.0
    net_cmd = conn.run("cat /proc/net/dev && echo '---' && sleep 0.3 && cat /proc/net/dev", hide=True, warn=True)
    if net_cmd.ok:
        parts = net_cmd.stdout.split("\n---\n")
        if len(parts) == 2:
            rx1, tx1 = _parse_proc_net_dev(parts[0])
            rx2, tx2 = _parse_proc_net_dev(parts[1])
            delta_rx = rx2 - rx1
            delta_tx = tx2 - tx1
            interval = 0.3
            if delta_rx > 0:
                net_rx_kbps = round((delta_rx / 1024) / interval, 2)
            if delta_tx > 0:
                net_tx_kbps = round((delta_tx / 1024) / interval, 2)

    # 8. Process count
    process_count = 0
    proc_result = conn.run("ps -eo pid --no-headers | wc -l", hide=True, warn=True)
    if proc_result.ok:
        try:
            process_count = int(proc_result.stdout.strip())
        except ValueError:
            process_count = 0
    top_cpu, top_mem = _collect_top_processes_remote(conn)
    return Metrics(
        cpu_percent=cpu_percent,
        cpu_cores=cpu_cores,
        cpu_per_core=cpu_per_core,
        mem_total_mb=_bytes_to_mb(mem_total),
        mem_used_mb=_bytes_to_mb(mem_used),
        mem_available_mb=_bytes_to_mb(mem_available),
        mem_percent=mem_percent,
        swap_total_mb=_bytes_to_mb(swap_total),
        swap_used_mb=_bytes_to_mb(swap_used),
        disk_total_gb=_bytes_to_gb(disk_total),
        disk_used_gb=_bytes_to_gb(disk_used),
        disk_percent=disk_percent,
        net_rx_kbps=net_rx_kbps,
        net_tx_kbps=net_tx_kbps,
        process_count=process_count,
        top_cpu=top_cpu,
        top_mem=top_mem,
        temp_c=temp_c,
        load1=load1,
        load5=load5,
        load15=load15,
        uptime_seconds=uptime_seconds,
    )


async def metrics_stream(interval: float) -> AsyncGenerator[Metrics, None]:
    """
    Async generator that yields metrics periodically for the LOCAL host.
    """
    # Ensure interval is sane.
    interval = max(interval, 0.5)

    while True:
        yield collect_metrics()
        await asyncio.sleep(interval)
