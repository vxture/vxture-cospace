# RGB-D原资料预览0.1

本机NYU受控路线的只读显示契约；Schema见[rgbd-input-preview-v0.1.schema.json](rgbd-input-preview-v0.1.schema.json)。原始观测仍采用现有report.json、PNM及已有tracking，显示数据不参与构建。

## 读取与授权

- `GET /api/inputs/{input_id}/rgbd-preview?space_id=…`：目录，最多500个accepted配对、1MiB响应。
- `GET /api/inputs/{input_id}/rgbd-preview/frame?space_id=…&frame_index=…`：一对显示图，最多2MiB响应；索引为目录中的accepted序号，非原报告数组序号。
- 两接口要求`data.manage`、当前Workspace／场景／资料归属；先授权后读取。`build.run`和`space.preview`不自动授予原资料权。`HEAD`同样执行授权；写方法拒绝。
- 严格查询参数；额外参数422、重复参数403、未认证401、无权／跨场景403，源内容或声明／位姿／索引核验失败409。无任意路径参数。响应`Cache-Control: no-store`。
- 能力在已有`/api/input-uploads`响应的`rgbd_input_preview`中声明；旧服务未声明时不尝试读取。

## 绑定与验证范围

目录固定space_id、input_id、snapshot_sha256及tracking_sha256，每帧含accepted `index`、原报告`source_index`、图像成员名／摘要、源时间／相对时间、RGB−深度配对时差与已有`T_anchor_camera`。已有位姿仅覆盖accepted前缀，缺项返回null。有限刚体矩阵、顺序、数量、成员命名、清单摘要及来源绑定均复核。仅有清单校验不代表原图已复核，`payload_checked:false`。

有完整可验证源时序时提供相对时间；旧资料无法得到源时刻时保留null，按帧序浏览。文件名时钟不宣称UTC同步；局部坐标为首深度相机、X右／Y下／Z前，不宣称场景对齐或重力方向。

单帧读取再次核对上述目录，并对被选两成员进行有界读取、大小和SHA-256校验、严格640×480 PNM解码。最大原成员2,000,000字节。其他图像不在本次解码范围，`payload_checked:selected_pair_only`；不写预检、不poll／启动任务、不选择或发布。源画面不可读不影响按自身证据可读的P18过程或固定发布。

## 显示规则

`display_rule:nyu-depth-metres-nearest-rgba/0.1`：

- RGB原P6通道保留，按[::2,::2]最近邻采样为320×240 RGB PNG。
- NYU深度PGM为小端原始码，沿现有适配器公式`z=351.3/(1092.5-code)`；保留code≥600、code<2047、有限且0<z≤10m的像素。这里是深度值有效性，不声称投影求解或最终建模像素全部有效。
- 固定色标t=z/10，RGB=`255*(t,1-|2t-1|,1-t)`取uint8；有效alpha255，无效RGBA全0。按[::2,::2]缩小，不以插值填补无效区域。
- `valid_depth_pixels`统计原640×480深度值有效像素，`invalid_depth:transparent`；两图保持各自原传感器画幅，不叠加假定已对齐。
- PNG由固定编码器生成，8位非交错，无外部资源，返回受限data:image/png;base64。客户端再核对绑定、帧映射、规则、尺寸、PNG签名和完整IHDR／IDAT／IEND块长度、CRC、无尾随数据及数量预算；浏览器图像错误清除两张图。目录流读取限制1MiB，图像响应限制2MiB，包含JSON空白。

全屏过程联动同时比对P18的过程帧index、源时刻、相对时间、双图摘要及完整估计位姿；目录明确映射到source_index。来源不同拒绝联动，不改写冻结过程记录。

质量固定`unverified`、`robot_ready:false`。本契约不表示通用RGB-D、设备流、标定修订、轨迹编辑或离线源图分发已支持。
