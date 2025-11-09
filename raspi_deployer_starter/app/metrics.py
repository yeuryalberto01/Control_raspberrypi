"""
System metrics collection utilities, supporting both local (psutil) and remote (SSH) hosts.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from typing import AsyncGenerator, Dict, List, Optional, Tuple

import psutil
from fabric import Connection

from .schemas import DiskPartitionMetric, Metrics, NetworkInterfaceMetric, ProcessMetric
from .system_ops import get_uptime_seconds


_CPU_TEMP_KEYS = {
    "cpu",
    "cpu-thermal",
    "soc_thermal",
    "coretemp",
    "k10temp",
    "bcpu",
}
_GPU_TEMP_KEYS = {
    "gpu",
    "gpu-thermal",
    "v3d",
    "video",
}


def _read_vcgencmd_temperature() -> Optional[float]:
    """Usa vcgencmd si est?? disponible para obtener la temperatura del SoC."""
    if shutil.which("vcgencmd") is None:
        return None
    try:
        result = subprocess.run(
            ["vcgencmd", "measure_temp"],
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return None
    match = re.search(r"temp=([\d\.]+)", result.stdout)
    if not match:
        return None
    try:
        return round(float(match.group(1)), 2)
    except ValueError:
        return None


def _read_temperatures() -> Tuple[Optional[float], Optional[float], Dict[str, float]]:
    """Lee las temperaturas disponibles y devuelve CPU, GPU y un mapa crudo."""
    try:
        temps = psutil.sensors_temperatures()
    except (AttributeError, NotImplementedError):
        temps = {}

    cpu_temp: Optional[float] = None
    gpu_temp: Optional[float] = None
    extra: Dict[str, float] = {}
    if temps:
        for label, entries in temps.items():
            label_lower = label.lower()
            for entry in entries:
                name = entry.label or label
                value = round(entry.current, 2)
                extra[name] = value
                name_lower = name.lower()
                if cpu_temp is None and (
                    label_lower in _CPU_TEMP_KEYS or "cpu" in name_lower or "soc" in name_lower
                ):
                    cpu_temp = value
                if gpu_temp is None and (
                    label_lower in _GPU_TEMP_KEYS or "gpu" in name_lower
                ):
                    gpu_temp = value

    if cpu_temp is None:
        cpu_temp = _read_vcgencmd_temperature()
        if cpu_temp is not None:
            extra.setdefault("vcgencmd", cpu_temp)

    return cpu_temp, gpu_temp, extra


def _read_temperature() -> Optional[float]:
    cpu_temp, _, _ = _read_temperatures()
    return cpu_temp


def _read_fan_speed() -> Optional[int]:
    """Devuelve la primera velocidad de ventilador disponible en RPM."""
    try:
        fans = psutil.sensors_fans()
    except (AttributeError, NotImplementedError):
        return None
    if not fans:
        return None
    for entries in fans.values():
        for entry in entries:
            if entry.current and entry.current > 0:
                return int(entry.current)
    return None


def _collect_disk_partitions() -> List[DiskPartitionMetric]:
    partitions: List[DiskPartitionMetric] = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, FileNotFoundError):
            continue
        partitions.append(
            DiskPartitionMetric(
                device=part.device,
                mountpoint=part.mountpoint,
                fstype=part.fstype,
                total_gb=_bytes_to_gb(usage.total),
                used_gb=_bytes_to_gb(usage.used),
                percent=round(usage.percent, 2),
            )
        )
    return partitions


def _collect_network_interfaces() -> List[NetworkInterfaceMetric]:
    interfaces: List[NetworkInterfaceMetric] = []
    stats = psutil.net_if_stats()
    addresses = psutil.net_if_addrs()
    mac_families = {
        af
        for af in (
            getattr(psutil, "AF_LINK", None),
            getattr(socket, "AF_PACKET", None),
        )
        if af is not None
    }

    for name, stat in stats.items():
        ipv4 = ipv6 = mac = None
        for addr in addresses.get(name, []):
            if addr.family == socket.AF_INET:
                ipv4 = addr.address
            elif addr.family == socket.AF_INET6:
                ipv6 = addr.address
            elif mac_families and addr.family in mac_families:
                mac = addr.address
        interfaces.append(
            NetworkInterfaceMetric(
                name=name,
                mac=mac,
                ipv4=ipv4,
                ipv6=ipv6,
                is_up=stat.isup,
                speed_mbps=stat.speed if stat.speed > 0 else None,
                mtu=stat.mtu if stat.mtu > 0 else None,
            )
        )
    return interfaces


@dataclass
class _NetSnapshot:
    timestamp: float
    rx_bytes: int
    tx_bytes: int


_LOCAL_NET_SNAPSHOT: Optional[_NetSnapshot] = None
_PROCESS_SAMPLE_INTERVAL = 0.15


@dataclass
class _ProcessSnapshot:
    timestamp: float
    process_count: int
    top_cpu: List[ProcessMetric]
    top_mem: List[ProcessMetric]
    limit: int


_PROCESS_SNAPSHOT: Optional[_ProcessSnapshot] = None
_PROCESS_SNAPSHOT_TTL = 2.0


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


def _collect_top_processes_local(limit: int = 5) -> Tuple[List[ProcessMetric], List[ProcessMetric], int]:
    process_count = len(psutil.pids())
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
    return top_cpu, top_mem, process_count


def _get_local_process_snapshot(limit: int = 5) -> Tuple[int, List[ProcessMetric], List[ProcessMetric]]:
    """
    Returns cached process metrics to avoid sampling psutil repeatedly across requests.
    """
    global _PROCESS_SNAPSHOT
    now = time.monotonic()
    snapshot = _PROCESS_SNAPSHOT
    if snapshot and (now - snapshot.timestamp) < _PROCESS_SNAPSHOT_TTL and limit <= snapshot.limit:
        return (
            snapshot.process_count,
            snapshot.top_cpu[:limit],
            snapshot.top_mem[:limit],
        )

    top_cpu, top_mem, process_count = _collect_top_processes_local(limit)
    _PROCESS_SNAPSHOT = _ProcessSnapshot(
        timestamp=now,
        process_count=process_count,
        top_cpu=top_cpu,
        top_mem=top_mem,
        limit=limit,
    )
    return process_count, top_cpu, top_mem


def collect_metrics() -> Metrics:
    """Collects metrics for the LOCAL host using psutil."""
    cpu_per_core = psutil.cpu_percent(interval=None, percpu=True) or []
    cpu_percent = sum(cpu_per_core) / len(cpu_per_core) if cpu_per_core else psutil.cpu_percent(interval=None)
    cpu_freq = psutil.cpu_freq()
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    swap = psutil.swap_memory()
    net_rx_kbps, net_tx_kbps = _read_local_network_rates()
    process_count, top_cpu, top_mem = _get_local_process_snapshot()
    cpu_temp, gpu_temp, extra_temps = _read_temperatures()
    fan_speed = _read_fan_speed()
    disk_partitions = _collect_disk_partitions()
    net_interfaces = _collect_network_interfaces()

    try:
        load1, load5, load15 = psutil.getloadavg()
    except (AttributeError, OSError):
        load1 = load5 = load15 = 0.0

    return Metrics(
        cpu_percent=round(cpu_percent, 2),
        cpu_cores=len(cpu_per_core) or (psutil.cpu_count(logical=True) or 0),
        cpu_per_core=[round(value, 2) for value in cpu_per_core],
        cpu_freq_current_mhz=round(cpu_freq.current, 2) if cpu_freq else None,
        cpu_freq_min_mhz=round(cpu_freq.min, 2) if cpu_freq and cpu_freq.min else None,
        cpu_freq_max_mhz=round(cpu_freq.max, 2) if cpu_freq and cpu_freq.max else None,
        mem_total_mb=_bytes_to_mb(mem.total),
        mem_used_mb=_bytes_to_mb(mem.used),
        mem_available_mb=_bytes_to_mb(getattr(mem, "available", 0)),
        mem_free_mb=_bytes_to_mb(getattr(mem, "free", 0)),
        mem_percent=round(mem.percent, 2),
        mem_cached_mb=_bytes_to_mb(getattr(mem, "cached", 0)) if hasattr(mem, "cached") else None,
        mem_buffers_mb=_bytes_to_mb(getattr(mem, "buffers", 0)) if hasattr(mem, "buffers") else None,
        swap_total_mb=_bytes_to_mb(swap.total),
        swap_used_mb=_bytes_to_mb(swap.used),
        swap_free_mb=_bytes_to_mb(getattr(swap, "free", 0)),
        disk_total_gb=_bytes_to_gb(disk.total),
        disk_used_gb=_bytes_to_gb(disk.used),
        disk_free_gb=_bytes_to_gb(disk.free),
        disk_percent=round(disk.percent, 2),
        disk_partitions=disk_partitions,
        net_rx_kbps=round(net_rx_kbps, 2),
        net_tx_kbps=round(net_tx_kbps, 2),
        net_interfaces=net_interfaces,
        process_count=process_count,
        top_cpu=top_cpu,
        top_mem=top_mem,
        temp_c=cpu_temp,
        gpu_temp_c=gpu_temp,
        fan_speed_rpm=fan_speed,
        extra_temperatures=extra_temps,
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

    # 2. Get Memory Info from /proc/meminfo
    mem_info = conn.run("cat /proc/meminfo", hide=True, warn=True)
    mem_total = mem_used = mem_available = mem_free = 0
    mem_cached = mem_buffers = None
    swap_total = swap_used = swap_free = 0
    mem_percent = 0.0
    if mem_info.ok:
        info_map: Dict[str, int] = {}
        for line in mem_info.stdout.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            match = re.search(r"(\d+)", value)
            if match:
                info_map[key.strip()] = int(match.group(1)) * 1024
        mem_total = info_map.get("MemTotal", 0)
        mem_available = info_map.get("MemAvailable", info_map.get("MemFree", 0))
        mem_free = info_map.get("MemFree", 0)
        mem_cached = info_map.get("Cached")
        mem_buffers = info_map.get("Buffers")
        if mem_total > 0:
            mem_used = max(mem_total - mem_available, 0)
            mem_percent = round((mem_used / mem_total) * 100, 2)
        swap_total = info_map.get("SwapTotal", 0)
        swap_free = info_map.get("SwapFree", 0)
        swap_used = max(swap_total - swap_free, 0)

    # 3. Get Disk Usage for all mounted filesystems
    disk_partitions: List[DiskPartitionMetric] = []
    disk_total, disk_used, disk_percent = 0, 0, 0.0
    disk_cmd = conn.run(
        "df -P -k --output=source,target,fstype,size,used,pcent",
        hide=True,
        warn=True,
    )
    if disk_cmd.ok:
        lines = disk_cmd.stdout.splitlines()
        for line in lines[1:]:
            parts = line.split()
            if len(parts) < 6:
                continue
            total_bytes = int(parts[3]) * 1024
            used_bytes = int(parts[4]) * 1024
            percent_match = re.search(r"(\d+)", parts[5])
            percent_value = float(percent_match.group(1)) if percent_match else 0.0
            percent_value = round(percent_value, 2)
            partition_metric = DiskPartitionMetric(
                device=parts[0],
                mountpoint=parts[1],
                fstype=parts[2],
                total_gb=_bytes_to_gb(total_bytes),
                used_gb=_bytes_to_gb(used_bytes),
                percent=percent_value,
            )
            disk_partitions.append(partition_metric)
            if disk_total == 0:
                disk_total = total_bytes
                disk_used = used_bytes
                disk_percent = percent_value
            if parts[1] == "/":
                disk_total = total_bytes
                disk_used = used_bytes
                disk_percent = percent_value

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
    disk_free = max(disk_total - disk_used, 0)
    extra_temps = {"vcgencmd": temp_c} if temp_c is not None else {}
    return Metrics(
        cpu_percent=cpu_percent,
        cpu_cores=cpu_cores,
        cpu_per_core=cpu_per_core,
        cpu_freq_current_mhz=None,
        cpu_freq_min_mhz=None,
        cpu_freq_max_mhz=None,
        mem_total_mb=_bytes_to_mb(mem_total),
        mem_used_mb=_bytes_to_mb(mem_used),
        mem_available_mb=_bytes_to_mb(mem_available),
        mem_free_mb=_bytes_to_mb(mem_free),
        mem_percent=mem_percent,
        mem_cached_mb=_bytes_to_mb(mem_cached) if mem_cached is not None else None,
        mem_buffers_mb=_bytes_to_mb(mem_buffers) if mem_buffers is not None else None,
        swap_total_mb=_bytes_to_mb(swap_total),
        swap_used_mb=_bytes_to_mb(swap_used),
        swap_free_mb=_bytes_to_mb(swap_free),
        disk_total_gb=_bytes_to_gb(disk_total),
        disk_used_gb=_bytes_to_gb(disk_used),
        disk_free_gb=_bytes_to_gb(disk_free),
        disk_percent=disk_percent,
        disk_partitions=disk_partitions,
        net_rx_kbps=net_rx_kbps,
        net_tx_kbps=net_tx_kbps,
        net_interfaces=[],
        process_count=process_count,
        top_cpu=top_cpu,
        top_mem=top_mem,
        temp_c=temp_c,
        gpu_temp_c=None,
        fan_speed_rpm=None,
        extra_temperatures=extra_temps,
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
