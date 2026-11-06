# Workspace 场景创建 P5b 验收

日期：2026-11-04。状态：本机实现与模拟平台验收通过；真实Vxture accounts生产联调未执行。

## 本批结果

核对平台规范080 §2.6与Yucer角色目录后，修正P5a的外部依赖假设：平台提供Workspace owner产品基线，产品内场景的创建、归属和细分功能授权由CoSpace实现，无需等待一个平台“创建三维场景”接口。

本批新增Workspace创建及来源分配配置、空场景在线创建、绑定当前验签Workspace、初始manager授权、持久幂等和中断恢复。数据管理增加DS创建对话框，成功后切换新场景；单场景manager不会自动获得创建新场景权限，须在部署配置中明确授予创建能力。Workspace owner在对应配置启用的scope具有创建基线，org owner及workspace manager不自动扩权。

新API只接收名称、说明、请求ID和上下文摘要。旧 `/api/spaces` POST及P5a初始化HTTP保持拒绝。新配置显式限制当前Workspace可选来源并固定来源指纹；撤销后不能新登记，既有资料仍保留。

## 验收证据

| 验证 | 结果 | 证据 |
| --- | --- | --- |
| 新创建／既有初始化／来源／场景权限／授权HTTP回归 | 168项通过，169.12秒 | `output/playwright/flow-batch-p5b-backend.log` |
| 最终创建及真实进程退出恢复测试 | 22项通过，28.99秒；21项与上行重叠，新增1项 | `output/playwright/flow-batch-p5b-initialization-final.log` |
| 不重复累计后端测试 | 169项 | 168＋22−21 |
| 独立服务真实HTTP／构建／重启 | 28项通过 | `var/validation/workspace-scenes-p5b-2026-11-04-001/acceptance.json` |
| 浏览器创建／响应丢失／刷新／越权／布局 | 20项通过 | `output/playwright/flow-batch-p5b-browser-result.txt` |
| TypeScript及Vite构建 | 通过；依赖已有use-client打包警告 | `output/playwright/flow-batch-p5b-build.log` |

真实HTTP覆盖：CSRF缺失、查看者无权、浏览器声明租户／项目拒绝、重复创建复用、请求ID换内容拒绝、跨Workspace直链拒绝、同请求ID跨Workspace独立、不同Workspace来源目录不同、越范围启用来源拒绝、已验签owner首个场景创建、来源撤销及历史资料保留、实际RP重启恢复。

新的 `space-47d9a5e9845f208d` 从空场景登记真实NYU短序列 `input-78d7a2edc80f4fbd`，预检通过，真实任务 `build-20aa96eb65084778` 完成模型与双视图。构建没有自动选择或发布。另一Workspace创建独立场景且只分配OS1来源。

浏览器实际提交创建后，验收脚本拦截确认响应并模拟503；服务端已创建。页面锁定原内容，刷新后恢复同一请求，“核对并重试”只得到一个场景。检查创建后定位数据管理、空资料／空构建／空发布、Workspace来源选择、查看者无按钮及直连403。1440／390px无全局横向溢出，创建对话框可见；新增按钮导致手机标题挤窄的问题已修正，最终截图已目视检查。

浏览器脚本可重复运行，每次会新增一个明确命名的独立验收场景；未删除中间验收记录来凑数量。最终截图：`output/playwright/flow-batch-p5b-create-1440.png`、`flow-batch-p5b-create-390.png`、`flow-batch-p5b-data-1440.png`。

## 保持与限制

原195个工程文件、8770原106个工程运行区文件哈希保持一致。8770未重启；8771使用独立复制运行区和本地模拟身份，不迁移8770的策略身份。完整汇总见 `output/playwright/flow-batch-p5b-acceptance.json`。

未完成真实accounts client／Workspace联调、产品成员角色管理UI、真实订阅／权益接入、任意文件上传以及自动判断物理场景重复。来源分配是可信部署管理配置，已有工程兼容路径不能当正式多租户部署。精度、定位、导航和实机消费不在本批范围；质量保持 `unverified / production_ready=false / robot_ready=false`。

契约见 [Workspace场景](../../contracts/schemas/workspace-scenes-v0.1.md)，操作见 [P5b运行](../guides/Workspace场景创建P5b运行.md)。下一步应将这些独立能力整理为数据管理的连续业务入口，减少用户在来源配置、导入、预检与构建之间寻找操作的次数；保持已验证的后端门禁。
