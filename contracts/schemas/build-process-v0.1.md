# 构建逐帧过程 0.1

状态：P18本机流程实现；精度`unverified`。附属于已有构建任务，不是发布或原始采集格式。

## 读取

`GET /api/build-process?space_id=…&candidate_id=…`。统一认证入口要求`build.run`，核对Workspace、场景、任务和登记资料归属，之后在线程池读取证据。拒绝额外／重复查询参数；响应`Cache-Control: no-store`。没有任意路径、帧变换、提高预算或触发计算的参数。

- 未认证401，无权／归属错误403，读取绑定或几何校验失败409，额外参数422；重复参数由统一门禁拒绝403。
- 旧任务返回`supported:false, reason:process_not_recorded`，不补造历史。
- 已启用记录但首个索引尚未保存：`supported:true, ready:false`；终止任务缺失索引返回409。
- 可读索引返回`supported:true, ready:true`及下述数据。

显示响应Schema：[build-process-v0.1.schema.json](build-process-v0.1.schema.json)。持久索引Schema：[build-process-index-v0.1.schema.json](build-process-index-v0.1.schema.json)。字段间一致性还需代码检查，Schema不替代摘要和数值校验。

## 持久化

新场景RGB-D任务只有已接受源帧具备严格递增整数`depth_time_us`时才声明`process_profile:cospace.build-process/0.1`。旧资料缺少帧时钟仍沿原路线构建；不自动补时间。

任务目录中的`process/process.json`为JSON索引，单一工作进程写临时文件后原子替换。每帧新增点以不可变`frame-NNNN.npz`保存，先写分块，再发布包含其字节数和SHA-256的索引修订。NPZ仅含`points`（float32，N×3）、`colors`（uint8，N×3），允许本帧N=0。索引含原始图像摘要、源帧时间、相对源时间、完整`T_anchor_camera`、各帧新增／累计点数及UTC处理时刻。

几何首次保留规则严格沿原构建：先在float64坐标上计算5厘米体素，保留每格首个样本，再转float32存储。过程按首次观测顺序；固定模型按原体素排序。冻结前逐点核对排序后的全量坐标和颜色，保留正式模型算法。不得从最终点数组顺序推断采集时间。

完成索引保存实际`spatial.npz`摘要；冻结元数据`construction_process`固定过程profile、原任务ID及完成索引SHA-256。冻结后的过程读取必须同时核对这些绑定与每帧分块。写入／终态完整性失败不能冻结；记录中的部分点不成为可发布模型。进程中断保留已原子保存的部分证据，API结合已保存任务状态呈现`interrupted/failed`。

## 数量与时间

每任务最多500帧、250万全量首次保留点、128MiB压缩分块；单块展开最多16MiB，索引最多1MiB。全量仅供过程与固定模型一致性及受限读取使用。

每次显示响应对累计已保存点按首次出现顺序做确定性步长抽样，全局最多10,000点、编码后最多2MiB；包含完整已保存几何的数值bounds。`first_seen_frames`与显示点、颜色逐项对应且非降序，播放第i帧时只绘制首次出现帧≤i的点。抽样步长可随已保存点数变化，画面是显示抽样，不承诺每次刷新保留相同显示子集；全量模型不受影响。轨迹只绘到当前游标帧。

三种时间分别使用：源帧`source_time_us/relative_time_us`、UTC处理时刻`processed_at`、浏览器播放器游标。当前源时钟明确为`filename_time_unverified_utc`，不将文件名时间转换成已核验UTC声明。已有位姿为估计相机位姿；后续缺少前缀位姿的帧计入`excluded_frames`并明确原因，不外推轨迹或填补观测。

过程终态与任务阶段分开：帧处理完成不代表双视图、人工核对或发布完成。接口不poll、不启动worker、不选择候选、不发布。普通读取不依赖原图像仍在线；以构建时已核验的图像摘要和冻结记录保存来源。离线交付沿用固定模型和两类视图，保留过程摘要引用，不包含逐帧过程分块，离线消费不据此获得过程回放功能。

## 页面

沿用P17新标签页全屏画布。新任务自动选择真实过程；静态资料和未记录旧任务保留明确标注的扫描演示，显示“此任务未记录逐帧过程”。跟随只读取已保存修订，回放使用相对源时间和明确倍率。网络失败暂停在最后核验画面；权限或绑定校验失败清空画面。回放不修改业务数据。
