# CoSpace 平台登记与真实联调：P25 收尾

> 后续部署已完成：正式域名 HTTPS、真实登录及服务器权益读取通过。最新状态见 [P27验收](../validation/正式域名部署与真实登录-P27-2026-11-06.md)。下文保留本批当时状态。

> 2026-11-06 后续更新：产品侧订阅门控和签名接收器已实现，真实 OBO / C2 未订阅读取已通过。正向订阅和真实回调投递尚待；以 [本批验收](../validation/Workspace订阅门控与回调-P25-2026-11-06.md) 为最新状态。下文保留登记时的阶段记录。

2026-11-06 更新：用户确定直接使用 stable 渠道、正式产品域名 cospace.ruyin.work、需要订阅、支持网页和桌面端。认证保持 accounts.vxture.com。原 beta／login_only 建议已由本版替代；此前交接ZIP与验收记录保留为历史证据。当前状态为**产品已登记为草稿、正式客户端已启用、8791真实登录通过**；订阅权益和生产部署尚未验收。见[真实登录记录](../validation/平台正式登记与真实登录-P25-2026-11-06.md)。

## 1. 登记交接材料

可直接核对填写的草稿：`deploy/config/cospace-platform-registration.draft.json`。它是产品侧交接单，**不是直接POST的平台API请求**；外层的purpose、origin、realm和待确认事项不是登录客户端提交字段。按Opera产品页的真实表单填写client子对象。

依据当前本机平台仓库：

- `docs/60-operations/40-register-a-product.md`：登记在Opera产品目录新建页完成；新客户端签发和回调调整要平台二次验证。
- `portals/opera/src/features/product/onboarding-model.ts`及`bff/opera-bff/src/routers/oidc-client.router.ts`：当前字段名、beta／stable渠道、机密客户端、PKCE和scopes。
- `bff/auth-bff/src/oidc/oidc.service.ts`：严格scope子集检查；授权码换票签发刷新令牌。
- `services/identity/iam/src/repository/pg-oidc-client.repository.ts`：当前产品realm为customer。旧080文档中的tenant不能直接照抄为登记值。

平台仓库路径是`D:\MyWebSite\vxture\vxture-platform`。本机源码仅读取；实际登记通过Opera页面提交，用户完成TOTP。已保存于`https://opera.vxture.com/product/catalog/cospace`，产品仍为草稿，没有执行上线。

## 2. 建议登记值

| 项目 | 建议填写 | 说明 |
| --- | --- | --- |
| 产品码 | cospace | 登记前核对唯一性；启用后不随意更名 |
| 产品名称／副名 | 空间态势服务／CoSpace | 与现有页面一致 |
| 类型／层级 | general_platform／L2 | 作为空间基础服务平台的建议分类，待平台管理员确认 |
| integrationMode | platform_managed | 需要订阅；开通、权益和用量接入须在上架前补齐，当前未实现 |
| 可独立订阅 | 开启 | 具体套餐、档位、价格在平台配置，不在产品内自定商业规则 |
| 端 | web、desktop | 产品目录终端声明；不表示桌面原生客户端已实现 |
| clientId／渠道 | cospace／stable | 一套正式渠道；不另建beta；临时本机回调联调后移除 |
| realm | customer | 当前产品客户端登记口径；不是workforce |
| 认证方式 | client_secret_basic | CoSpace有服务端，可保存密钥；不选公共客户端none |
| PKCE | 开启，S256 | 应用已实现 |
| allowedScopes | openid profile email | 与应用请求完全一致；不请求phone、offline_access或商业订阅scope |
| 后端通道登出地址 | 留空 | 当前未实现logout_token接收路由 |
| sloParticipation | none | 中央视图采用session/status检测及RP主动全局登出；不虚填后台登出地址 |

### 本机真实平台联调：同一stable客户端，独立8791端口

```text
Origin:                  http://127.0.0.1:8791
redirectUris:            http://127.0.0.1:8791/auth/callback
postLogoutRedirectUris:  http://127.0.0.1:8791/workbench/layout.html
```

平台管理员须确认该loopback联调回调可登记；不把网页服务改成公共客户端来绕过登记要求。8790继续保留现有mock演示及P28成果。127.0.0.1只能由本机浏览器访问，平台远端探活不能据此判断服务已公网部署。

### 正式地址已确定，尚未部署验收

```text
Origin:                  https://cospace.ruyin.work
redirectUris:            https://cospace.ruyin.work/auth/callback
postLogoutRedirectUris:  https://cospace.ruyin.work/workbench/layout.html
webhookUrl:             https://cospace.ruyin.work/api/webhooks/vxture
```

本机已解析A记录39.103.62.17；HTTPS请求当前握手失败，尚未确认原因，不能视为HTTPS或产品部署完成。该域名需要覆盖ruyin.work子域的有效证书和对应vhost；边缘上游须来自实际CoSpace部署，不能填写DNS边缘IP冒充业务上游。当前表单上游留空。认证发行者及认证端点仍在accounts.vxture.com，不随产品域名迁移。

## 3. 客户端签发后的本机配置

`deploy/config/cospace-platform-production.env.example`为正式环境模板，`cospace-platform-local.env.example`为同一stable客户端的临时本机联调模板。只含非秘密配置，不能把平台secret写回模板。平台首次签发返回的Client Secret交给本机私有环境或秘密管理器；另生成稳定的Fernet会话密钥。二者均不进入聊天、Git、业务备份或登记交接ZIP。

| 环境变量 | 来源 |
| --- | --- |
| COSPACE_OIDC_CLIENT_ID | cospace，以平台实际签发值为准 |
| COSPACE_OIDC_CLIENT_SECRET | 平台签发secret |
| COSPACE_OIDC_ISSUER | https://accounts.vxture.com |
| COSPACE_OIDC_BACKCHANNEL | 本机默认同上；生产内部通路以平台实际网络配置为准 |
| COSPACE_ORIGIN | 正式https://cospace.ruyin.work；本机http://127.0.0.1:8791 |
| COSPACE_OIDC_LOOPBACK_HTTP | 本机联调为1；正式HTTPS配置为0 |
| COSPACE_SESSION_KEY | 本机独立生成并安全持有的稳定Fernet密钥 |

会话密钥不能每次启动重生成，否则已有会话无法解密。COSPACE_SESSION_KEY不是平台签发项，也不能用Client Secret代替。

先运行只读预检，输出使用新文件名：

```powershell
.venv/Scripts/python.exe -X utf8 -m experiments.scripts.check_platform_readiness --output output/playwright/p25-real-preflight-NEW.json
```

预检检查公开端点、公钥、应用请求scope和配置缺项，不等于真实登录通过。

## 4. 真实Workspace和数据隔离

平台Workspace表示租户业务边界，不是一个用户。平台登记客户端也不会自动获得访问所有Workspace或场景的权利。

部署方准备独立的`var/platform-p25`业务根及`var/platform-p25-state`会话目录；**不从var/trial复制mock租户绑定**。本次只创建了私有state目录用于认证验证，没有创建或授权真实业务根。

```text
var/platform-p25/
  runtime/   # 新场景业务资料及成果
  policy/    # 显式初始化的空SpaceAccessPolicy
  setup/
    sources.json           # 空的cospace.preview-sources/0.1
    workspace-scenes.json  # 从disabled模板起步，确认租户后再启用
    consumer-access.json   # audience=cospace，起步无grants
var/platform-p25-state/
  sessions/                # 环境密钥加密的真实RP会话
```

可复用的默认关闭配置：`deploy/config/cospace-workspace-scenes.disabled.json`和`cospace-consumer-access.disabled.json`。前者已按WorkspaceSceneConfig校验，后者按ConsumerConfig校验。都不包含真实租户或授权。

登记完成后需平台给出测试的真实org_id、workspace_id、所有者sub、普通成员sub及第二个隔离Workspace。不能用名称或示例值当真实身份。

```json
{
  "profile": "cospace.workspace-scenes/0.1",
  "revision": 2,
  "workspaces": [{
    "issuer": "https://accounts.vxture.com",
    "org_id": "替换为真实组织ID",
    "workspace_id": "替换为真实Workspace ID",
    "allow_create": true,
    "creator_subjects": [],
    "source_bindings": {}
  }]
}
```

上面是填写示意，不是可直接启用的配置。真实Workspace所有者可在获启用的范围创建场景；普通成员按场景产品角色授权。格式校验不代替身份来源核对。

## 5. P26真实程序消费的额外条件

网页登录登记完成，不等于产品换票完成。独立消费程序应使用**调用产品自己的客户端**；平台按调用产品在指定Workspace的真实覆盖／订阅或provisioned状态决定能否签发service票据，CoSpace再按caller与场景授权检查。

目标audience为cospace；service票据含act.sub、org_id、workspace_id，不能拿浏览器Cookie、CoSpace RP secret或用户OBO票据代替。当前登记目标为platform_managed，但产品的权益拉取、验签回调及用量上报仍未实现，不能标为已开通。平台需要哪些真实调用产品及覆盖，作为独立联调输入提供，不创建一套产品侧商业白名单替代平台覆盖。

### 订阅接入的最小闭环

平台以Workspace×product为维度决定订阅和权益，CoSpace保留现有场景角色控制，二者同时满足才允许业务访问。身份认证成功不能替代有效权益，Workspace所有者也不能绕过订阅。

1. **C2实时权益**：按平台product_200／product_220契约请求`/platform/entitlements`；短TTL缓存、失效即重拉，不把权益塞进OIDC token或永久复制进业务库。UI按`tier != null`，数据面按`tier != null || bundled`，再与场景授权相交。平台异常或未知状态不放宽权限。
2. **C3开通与失效**：标准路径`POST /api/webhooks/vxture`，实现平台规定的HMAC校验、重放防护及幂等处理；接开通、撤销、订阅变更／失效，撤销不自动删除历史场景。不能仅收到一条通知就永久授予商业访问权。
3. **套餐与订阅入口**：套餐、档位、定价归平台；产品仅在用户点击后跳转`https://console.vxture.com/subscribe?product=cospace&intent=subscribe`，不自动购买或创建付费订阅。
4. **用量**：先确定实际计费指标与计量时点，再走平台consume；不重复上报模型token，不虚造指标、价格或套餐。本次尚未登记指标。
5. **验收**：未订阅拒绝业务访问；平台测试Workspace真实开通后可使用；撤销／到期后权限失效；跨Workspace拒绝；签名错误、重复／过期通知、平台不可用均验证保守处理。

上述是待实施项，当前仅更新登记配置；在闭环和HTTPS验收前，产品保持草稿，不执行“确认上线”。桌面端当前为产品形态登记，不把机密客户端secret打入桌面安装包；原生登录回调和公共客户端策略另行按实际客户端确定。

## 6. 登记后实际验收顺序

| 验收 | 实际操作与预期 | 当前 |
| --- | --- | --- |
| 注册回执 | 核对产品／渠道clientId、精确回调、scopes；secret本机保存 | 已通过，产品草稿、stable客户端启用 |
| 登录／回调 | 本机8791跳转真实accounts，PKCE、nonce、单次state、业务会话成功 | 已通过，身份验证入口，业务关闭 |
| 刷新 | 真实access过期后单次轮换refresh，页面会话继续 | 待真实配置 |
| 中央状态／登出 | accounts主动登出或失效后，经status确认结束；错误不误判退出 | 真实status通过，主动全局登出未执行 |
| Workspace隔离 | A创建资料／发布，B和未授权成员直接ID访问被拒 | 待真实租户 |
| 成员撤权 | 下一业务请求权限失效，不凭前端隐藏判断通过 | 待真实租户 |
| 程序换票 | 真实调用产品在真实Workspace换票并查固定发布；未覆盖／错场景拒绝 | 待调用方客户端与覆盖 |
| 业务主线 | 上传、预检、批次、构建、双视图、核对、固定发布、历史查询 | 待上述真实身份条件 |

真实登录及中央状态已通过；真实Workspace的业务权限、订阅门控和service换票仍未验收。下一批完成订阅最小闭环后再开放业务，不能以本轮登录成功替代商业与场景授权验收。

## 7. 当前本机身份验证入口

地址`http://127.0.0.1:8791/workbench/layout.html`；使用现有`serve_platform_auth`身份验证模式，`business_authorization=false`，所有业务接口关闭。8790继续保留模拟演示。两者的本机HTTP Cookie同名且端口不隔离，在同一浏览器来回访问可能需要重新登录；服务会话与业务文件隔离，正式HTTPS域名使用独立的__Host-cookie。

本机私有凭据保存在被Git忽略的`var/platform-p25-state`，Windows当前用户DPAPI加密，目录ACL仅当前用户与SYSTEM。Fernet会话密钥稳定保存；禁止复制到交接包。以下命令不打印秘密，使用同一Windows用户运行：

```powershell
& './var/platform-p25-state/launch-local.ps1' -Action run
```

当前运行会话由本轮工具保持；不要重复启动占用8791。`-Action check`和`-Action verify`输出为独占验收文件，本轮已运行，不能覆盖历史结果。此入口仅证明认证接入，不是P27生产部署或可订阅业务上线。
