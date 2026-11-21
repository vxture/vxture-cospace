# 空间基准 B07 阶段发布候选

生产基线 v0.12.0。候选包含场景配准资料、独立审核与采用、WGS84 局部 ENU 适配、二维/三维对象点锚及固定在线/离线交付。版本标签、生产审核和上线结果以 GitHub 及后续部署记录为准。

## 配置与数据

新数据库为 /srv/md0/cospace/data/business/runtime/preview-directory/scene-registrations.sqlite3。只在首次写入创建，部署 checkpoint 已纳入；不更改既有本体数据库与旧发布。新成果成员 registration-artifact.json 位于既有固定发布目录，完整离线包 profile 为0.6。新版支持旧包，旧客户端不支持0.6；分区包明确拒绝包含新闭包的发布。

宿主可选文件 /srv/md0/cospace/etc/registration.env 声明 COSPACE_REGISTRATION_ADAPTERS=wgs84_local_enu/1（无凭据）。空值停用工作数据地理定位和新配准成果发布；已有固定成果自带闭包继续按固定有效期读取，停用分发应使用暂停/退役；不删除历史核准与工作资料。Compose 通过可选 env_file 读取，已有地图密钥与地球配置沿用私有文件。此配置归宿主引擎配置管理，不放入公共资源本体。没有原点测量资料的场景继续工程坐标核对，不借场景入口位置自动配准。

## 发布流程与验收

feature PR 经 quality-gate、build、test-coverage、audit、gitleaks 五项检查后 squash 合并；核对 main 的同提交检查后创建未使用的版本标签，由 GitHub 构建固定镜像。production Environment reviewer 审核后部署 vx-worker-02，栈根 /srv/md0/cospace。不得上传本地源码包，不以 main push 代替发布。

部署前记录旧镜像，验证数据库 checkpoint complete、quick_check 和固定成果备份；部署后核对三服务健康、IFC 通道、OCI 提交及 VERSION、公网静态资源与匿名业务拒绝。正式身份验收需导入真实控制资料，由另一位场景管理员审核采用；工程合成测试不代表现场精度通过。

## 回退

v0.12.0 不理解配准闭包，可能导出遗漏资料的旧包。回退前停止新写入、暂停所有带 registration_selection 的新发布并验证读取/导出被拒绝，再备份生命周期库、工作数据库与固定发布目录。无法证明已隔离全部新成果时保持流量隔离，发布修复版本，不直接恢复旧代码分发。

保留新数据库与成果文件，保留暂停/退役隔离状态。通过已验证旧提交创建新的回退标签，仍由 GitHub 构建和生产审核。禁止旧版本恢复新成果分发；恢复分发前先升级支持0.6的版本并重新核对。应用回退不自动还原数据库，不在线覆盖SQLite/WAL，不改写已有标签。
