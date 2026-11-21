# 空间配准候选合同 0.1（B07a）

`spatial-registration-input-v0.1.schema.json` 来自 `packages.spatial.georeference.RegistrationInput.model_json_schema()`；运行时额外验证浮点有限性、刚体正交/正行列式、固定来源、范围及控制组退化。JSON Schema 结构通过不能替代完整计算验证。

核对器要求宿主从已授权固定模型读取 expected_source。请求中没有可信主体、权限或批准字段；B07a 无 HTTP、数据库、生产入口及发布集成。单位仅 m，源右手轴定义必填，目标 east/north/up，矩阵为列向量 `p_target = R * p_source + t`、最后行为 `[0,0,0,1]`、3x3 R 不允许缩放/反射/剪切。当前只核对已有参数，不拟合。

输入包含明确 synthetic 标识；所有合成算例仅本地开发使用。controls 中 fit 为参数建立控制组，check 为独立留出检查组；两组各至少三个非共线点。重复标识、重复源/目标坐标拒绝。工程上的分组检查不证明证据真实或现场独立。

结果 profile 为 `cospace.spatial-registration-candidate/0.1`。input_sha256 绑定规范化全输入；逐点 predicted_m、delta_m 为“变换源点减目标点”；horizontal_m 为 XY 欧氏差、vertical_m 为绝对 Z 差。两组各输出水平/垂直 RMSE 和最大值；calculation_status 仅由检查组逐点是否同时满足两个门限决定。计算通过仍保持 review_status=not_reviewed、control_evidence_verified=false、can_focus_geographic_map=false、robot_ready=false。

metric target 的参考系标识不自动授予经纬度转换能力。geographic_adapter 固定 not_connected，禁止把源局部坐标或目标工程坐标直接用作地图经纬度。正式投影、高程/格网依赖、有效期、审核持久化和固定地理发布属于 B07b—d 的后续合同。

可视化读取同一输入与计算报告；水平/高程误差和门限必须标单位，配准前/后仅切换空间显示。表格、模型标记、目标标记、误差图共享控制点身份。主图显示真实坐标差，不能把放大误差当实际位置。缺几何时继续提供控制点及误差清单。依据和参数按需抽屉查看。
