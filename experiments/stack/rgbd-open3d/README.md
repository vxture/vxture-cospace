# 隔离 RGB-D 里程计试验

Open3D 0.19.0，Python 3.12；仅用于研究对照。根项目继续使用 Python 3.14，根依赖和 API 不引入 Open3D。精确依赖及发行包摘要见本目录 `uv.lock`，本轮实际安装使用清华 PyPI 镜像（官方源 TLS 连接失败），镜像地址已写入锁文件。

从仓库根目录运行：

```powershell
uv sync --locked --project experiments/stack/rgbd-open3d --python 3.12 --cache-dir .cache/uv --default-index https://pypi.tuna.tsinghua.edu.cn/simple
.venv/Scripts/python.exe -m experiments.scripts.prepare_nyu_open3d var/nyu/office-0001a-short-001 --output var/nyu/office-0001a-rectified-NEW
$env:OMP_NUM_THREADS='2'
$env:OPENBLAS_NUM_THREADS='2'
experiments/stack/rgbd-open3d/.venv/Scripts/python.exe -m unittest discover -s tests -p test_open3d_hybrid_runtime.py -v
experiments/stack/rgbd-open3d/.venv/Scripts/python.exe -m experiments.scripts.run_nyu_open3d var/nyu/office-0001a-rectified-NEW --baseline var/nyu/office-0001a-multiscale-001/comparison.json --output var/nyu/office-0001a-open3d-NEW
.venv/Scripts/python.exe -m experiments.scripts.check_nyu_open3d var/nyu/office-0001a-open3d-NEW --prepared var/nyu/office-0001a-rectified-NEW --baseline var/nyu/office-0001a-multiscale-001/comparison.json --output experiments/evidence/2026-10-28/nyu-open3d-NEW
```

所有输出目录必须全新，原始资料与大文件保留在忽略的 `var/`。准备器核验快照摘要、执行深度单位转换与反畸变、最近 Z 光栅化；空洞保持 0。仅保留有投影颜色的像素，不进行补洞。它不证明彩深外参、运动补偿或遮挡一致性正确。

运行器对每对帧独立从单位变换估计正反向运动；Open3D 返回 source→target，正向调用 current→previous，反向调用 previous→current。报告反向子对象复用了 `T_previous_current` 字段名，其实际方向是 previous→current，以调用方向为准。最终几何检查使用原始 stride=4 点云，与旧实验保持同一表示与阈值。库 success 不等同于旧求解器收敛指标或独立精度验证。

7 项 Open3D 运行时测试必须在此隔离环境执行；根环境会明确跳过，不能用根环境跳过结果代替实际执行。MIT 许可原文随本轮证据保留；这不代表已完成全部传递依赖和原始数据许可的商用审查。

约束分离：运行器新增 `--mode hybrid|constant-color|color-only`，默认hybrid。constant-color将输入设为128，保留混合目标及相同有效深度；color-only使用颜色雅可比，仍依赖深度关联。每个模式写独立新目录。输入诊断脚本为 `experiments.scripts.diagnose_nyu_alignment`（使用本环境已有Pillow），汇总为 `experiments.scripts.summarize_nyu_ablation`（根环境），详见[验证](../../../docs/validation/NYU彩深配准与约束分离验证-2026-10-28.md)。

空洞近邻敏感性：新增 `--hole-margin 0|4`，默认0。设4时，排除缺失深度的4px方形近邻及图像边框，颜色保持不变；最终共同几何检查仍用完整原始点云。每帧掩膜摘要、原始/保留像素数记录在报告中，独立检查器复算。内部金字塔可能传播边缘效应，不代表完全屏蔽颜色边界。空间残差图入口为 `experiments.scripts.diagnose_nyu_residuals`，详见[验证与复现](../../../docs/validation/NYU断点残差与空洞近邻对照-2026-10-28.md)。
