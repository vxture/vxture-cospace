# 构建

jobs.py负责固定输入的synthetic_check任务提交及执行编排。执行和存储通过装配传入的适配器调用，不依赖数据库或具体进程库。错误规范位于errors.py。

当前只产生合成检查报告，不产生空间候选、真值或发布。每job仅一次attempt；不支持自动恢复或重试。任务Schema在contracts，worker入口在apps/worker，事务及进程实现位于infrastructure。

运行及限制见[手册](../../docs/guides/本地检查任务运行.md)。
