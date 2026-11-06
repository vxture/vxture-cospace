# 合成空间查询 API

## 数据库托管入口

配置COSPACE_DATABASE_URL为专用PostgreSQL演示库，先通过本地CLI登记及激活样例，再运行：

```sh
uv run --locked uvicorn apps.api.managed:managed_app --factory --host 127.0.0.1 --port 8000
```

GET /scenes/{scene_id}/current返回当前指针、revision及active状态；GET /scenes/{scene_id}/releases/{release_id}追溯内容及撤回记录；POST /query接受同样的固定版本点请求。每次查询检查当前撤回状态，撤回为410、未知版本404、坐标冲突409、存储不可用或损坏503，不伪装为空间unknown。

数据库托管入口无写入HTTP操作；注册、切换和撤回仅提供本地CLI。当前仍无认证，不对外暴露。以下无数据库/sample入口仅为固定快照演示，不受托管撤回系统管理，不能把它用于需要当前有效性检查的消费。

## 无数据库快照入口

仅供本机开发验证；当前无身份认证、正式采用、发布指针和撤回。不要公开监听或接入真实交付。

从仓库根目录启动：

```powershell
uv sync --locked
uv run --locked uvicorn apps.api.main:demo_app --factory --host 127.0.0.1 --port 8000
```

默认加载examples/indoor-spatial，可通过服务端环境变量COSPACE_SAMPLE_ROOT指定本地包；HTTP请求不能指定文件路径。载入失败时拒绝服务，运行中持有已校验内存快照。停止并重新启动才加载新包。

- GET /sample：读取固定版本、摘要及合成标记。
- POST /sample/query：请求scene_id、release_id、frame_id和point（长度3的JSON数值数组）。
- GET /openapi.json及/docs：试验接口规范与交互文档。

示例请求：

```json
{"scene_id":"synthetic-equipment-corridor","release_id":"release-spatial-sample-001","frame_id":"sample-local","point":[5,3,1]}
```

有效点返回200及occupied、observed_free、unknown或out_of_scope。版本和坐标不匹配返回409及detail.code；字段、非有限值或坐标数量错误返回422。响应始终data_kind=synthetic、real_release_ready=false；passed字段继承包校验结果，不表示点可通行或质量达标。接口尚未对外承诺兼容。

## 托管合成人视图

数据库模式的apps.api.managed提供GET /scenes/{scene_id}/releases/{release_id}/human，返回固定发布、真值版本、人视图版本、坐标定义、摘要、对象锚点、有效状态分区及证据。此路径不属于上述无数据库快照入口。

synthetic_cells_v0.1仅为已登记合成包的预览投影；分区沿全部输入边界切分，并复用点查询规则，未知和冲突不能转为空闲。上限4096块，超出返回409/preview_too_complex，待后续瓦片设计；不截断或降级为虚假空闲。旧快照缺少对象内容时返回409/human_view_unavailable。

读取预览与撤回使用同一场景事务锁；当前保守策略在synthetic_point_query撤回后同时阻止预览（410），元数据追溯仍可用。这是合成子集策略，不表示已建立独立的人视图能力撤回体系。已下载的浏览器快照不支持远程收回；加载与查询时检查，不声称实时撤销客户端数据。

## 固定发布的数据与本体核对

托管模式新增GET /scenes/{scene_id}/releases/{release_id}/data与/ontology，字段、状态和兼容边界见[投影契约](../../contracts/schemas/release-inspection-v0.1.md)。二者每次读取均检查撤回，旧快照缺少内容返回409/inspection_unavailable；内容校验不一致返回503，不能显示为规则通过。接口不接收文件路径或写入动作。

## 只读任务工作面

设置COSPACE_DATA_ROOT为实际导入/任务存储根目录后，托管API提供场景任务列表、详情、input和report的GET接口；未配置返回503。请求字段、分页和错误见[契约](../../contracts/schemas/job-reading-v0.1.md)。任务按场景读取，与当前服务发布和空间消费撤回分别管理，不新增网络任务运行/取消操作。仅用于本机未认证开发环境。
