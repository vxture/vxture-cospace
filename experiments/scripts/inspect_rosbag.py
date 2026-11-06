"""Inspect ROS1 input metadata; no claim of calibration, geometry or algorithm validity."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics

import rosbag


def inspect(path, lidar_topic, imu_topic):
    streams = {}
    errors = []
    with rosbag.Bag(str(path), "r") as bag:
        for topic, msg, recorded in bag.read_messages(topics=[lidar_topic, imu_topic]):
            state = streams.setdefault(topic, {
                "count": 0, "type": msg._type, "frames": set(), "fields": set(),
                "stamps": [], "backward_steps": 0, "duplicate_steps": 0,
                "invalid_numeric_messages": 0, "points": 0, "invalid_cloud_fields": 0,
            })
            state["count"] += 1
            stamp = msg.header.stamp.to_sec() if hasattr(msg, "header") else None
            if stamp is None or not math.isfinite(stamp) or stamp <= 0:
                errors.append(f"{topic}: invalid or absent header timestamp")
            else:
                if state["stamps"]:
                    delta = stamp - state["stamps"][-1]
                    state["backward_steps"] += int(delta < 0)
                    state["duplicate_steps"] += int(delta == 0)
                state["stamps"].append(stamp)
            if hasattr(msg, "header"):
                state["frames"].add(msg.header.frame_id)
            if msg._type == "sensor_msgs/PointCloud2":
                current_fields = {f.name for f in msg.fields}
                state["fields"].update(current_fields)
                state["invalid_cloud_fields"] += int(
                    not {"x", "y", "z"}.issubset(current_fields)
                    or not {"time", "t", "timestamp"}.intersection(current_fields))
                state["points"] += msg.width * msg.height
            elif msg._type == "sensor_msgs/Imu":
                values = [getattr(v, axis) for v in
                          (msg.linear_acceleration, msg.angular_velocity)
                          for axis in ("x", "y", "z")]
                state["invalid_numeric_messages"] += int(not all(map(math.isfinite, values)))
    for topic, expected in ((lidar_topic, "sensor_msgs/PointCloud2"),
                            (imu_topic, "sensor_msgs/Imu")):
        if topic not in streams:
            errors.append(f"{topic}: missing topic")
        elif streams[topic]["type"] != expected:
            errors.append(f"{topic}: expected {expected}, found {streams[topic]['type']}")
    for topic, state in streams.items():
        stamps = state.pop("stamps")
        intervals = [b - a for a, b in zip(stamps, stamps[1:]) if b > a]
        state["frames"] = sorted(state["frames"])
        state["fields"] = sorted(state["fields"])
        state["start"] = min(stamps) if stamps else None
        state["end"] = max(stamps) if stamps else None
        state["median_interval_seconds"] = statistics.median(intervals) if intervals else None
        state["max_positive_interval_seconds"] = max(intervals) if intervals else None
        if state["backward_steps"] or state["duplicate_steps"]:
            errors.append(f"{topic}: non-increasing header timestamps")
        if state["invalid_numeric_messages"]:
            errors.append(f"{topic}: invalid IMU numeric values")
        if state["invalid_cloud_fields"]:
            errors.append(f"{topic}: messages with incomplete xyz or point-time fields")
        if state["count"] < 2:
            errors.append(f"{topic}: insufficient messages for temporal precheck")
        if "" in state["frames"]:
            errors.append(f"{topic}: empty frame identifier")
    fields = set(streams.get(lidar_topic, {}).get("fields", []))
    if not {"x", "y", "z"}.issubset(fields):
        errors.append("lidar: missing xyz fields")
    if not {"time", "t", "timestamp"}.intersection(fields):
        errors.append("lidar: no recognized point-time field; adapter review required")
    overlap = None
    if lidar_topic in streams and imu_topic in streams:
        left, right = streams[lidar_topic], streams[imu_topic]
        if all(s["start"] is not None for s in (left, right)):
            overlap = max(0.0, min(left["end"], right["end"]) - max(left["start"], right["start"]))
            if overlap <= 0:
                errors.append("lidar/imu: no positive header-time overlap")
    digest = hashlib.sha256()
    with path.open("rb") as raw:
        for block in iter(lambda: raw.read(1024 * 1024), b""):
            digest.update(block)
    return {
        "scope": "ROS1 PointCloud2/Imu structural precheck only",
        "file": str(path), "sha256": digest.hexdigest(), "streams": streams,
        "header_time_overlap_seconds": overlap,
        "errors": sorted(set(errors)),
        "structural_precheck_passed": not errors,
        "algorithm_ready": False,
        "unverified": ["point-time unit and per-point contents", "clock synchronization",
                       "extrinsics and IMU convention", "ring semantics and required IMU attitude",
                       "license and dataset provenance", "geometry and localization quality"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("bag", type=Path)
    parser.add_argument("--lidar-topic", default="/points_raw")
    parser.add_argument("--imu-topic", default="/imu")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = inspect(args.bag, args.lidar_topic, args.imu_topic)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"structural_precheck_passed": report["structural_precheck_passed"],
                      "errors": report["errors"]}))
    return 0 if report["structural_precheck_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
