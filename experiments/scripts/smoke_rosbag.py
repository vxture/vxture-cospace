"""Synthetic fixtures verify input rejection, not SLAM or real-world quality."""
import json
from pathlib import Path
import sys

import rosbag
import rospy
from sensor_msgs.msg import Imu, PointField
from sensor_msgs import point_cloud2
from std_msgs.msg import Header

from inspect_rosbag import inspect


def create(path, missing_time=False, backward=False):
    fields = [PointField(name, i * 4, PointField.FLOAT32, 1)
              for i, name in enumerate(["x", "y", "z", "intensity"])]
    fields.append(PointField("ring", 16, PointField.UINT16, 1))
    if not missing_time:
        fields.append(PointField("time", 18, PointField.FLOAT32, 1))
    with rosbag.Bag(str(path), "w") as bag:
        for i in range(201):
            at = rospy.Time.from_sec(100.0 + i * .005)
            imu = Imu()
            imu.header = Header(stamp=at, frame_id="imu")
            if backward and i == 100:
                imu.header.stamp = rospy.Time.from_sec(100.0)
            imu.orientation.w = 1.0
            imu.linear_acceleration.z = 9.81
            bag.write("/imu", imu, at)
            if i % 20 == 0:
                points = [(1., float(j), .5, 1., j % 16) +
                          (() if missing_time else (j * .001,)) for j in range(16)]
                cloud = point_cloud2.create_cloud(Header(stamp=at, frame_id="lidar"), fields, points)
                bag.write("/points_raw", cloud, at)


def main():
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    results = []
    for name, missing, backward, expected in (
        ("synthetic_valid_structure", False, False, True),
        ("synthetic_missing_point_time", True, False, False),
        ("synthetic_backward_imu", False, True, False),
    ):
        bag = output / (name + ".bag")
        create(bag, missing, backward)
        report = inspect(bag, "/points_raw", "/imu")
        (output / (name + ".json")).write_text(json.dumps(report, indent=2), encoding="utf-8")
        results.append({"case": name, "expected": expected,
                        "actual": report["structural_precheck_passed"], "errors": report["errors"]})
    summary = {"data_kind": "synthetic_test_fixture_not_truth",
               "cases": results, "passed": all(r["actual"] == r["expected"] for r in results),
               "slam_executed": False}
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
