# 平台 RP 会话 HTTP 契约 v0.1

本契约描述I2独立认证模式及I3业务授权装配。真实平台客户端仍需独立登记和联调。

| 路由 | 语义 |
| --- | --- |
| GET /api/auth/config | 返回enabled/mode/business_authorization；不含issuer secret、client secret或token |
| GET /auth/login?returnTo=... | 顶层302到平台authorize；returnTo仅允许/workbench/内相对路径，拒绝跳域、控制字符与目录穿越 |
| GET /auth/callback | 浏览器绑定state单次消费，交换code、验nonce/sub/sid及双token，302到已保存路径；拒绝重复query参数 |
| GET /api/auth/session | 返回保存身份、csrf和authority_state；不触发中央活动、不刷新access token、不决定到期登出 |
| POST /api/auth/session | 同源Origin+X-CoSpace-CSRF；按中央next_check_at到期查询，失败保留会话并按短重试间隔重查 |
| POST /auth/logout | 同源Origin+表单csrf；清会话和Cookie，303到平台end_session，携带id_token_hint及已登记返回地址 |

认证模式config为`{enabled:true,mode:"identity_pilot",business_authorization:false}`；I3业务模式为`{enabled:true,mode:"authorized_workbench",business_authorization:true}`；原工程预览为`{enabled:false,mode:"engineering_preview",business_authorization:false}`。业务模式在挂载业务应用前必须同时装配空间授权中间件，缺一拒绝创建应用。

session的公共字段：`enabled`、`authenticated`、`authority_state`（cached/confirmed/unavailable/signed_out）、`mode`、`business_authorization`。有会话时另带`user:{subject,org_id,workspace_id,display_name}`、`csrf`、`access_ready`。`cached`指已保存快照，不是刚得到中央确认；access_ready不是空间授权或机器人运行放行。

认证失败不回显上游error_description、code、JWT或密钥。平台或加密存储不可用返回503；CSRF/Origin拒绝返回403；业务API无会话401。identity_pilot中有会话的业务调用仍返回503；authorized_workbench中还必须通过当前凭据、中央确认有效期与空间策略检查，无权限返回403，策略或中央确认不可用返回503。所有响应Cache-Control:no-store；生产会话Cookie为host-only HttpOnly Secure SameSite=Lax。

登录存储没有自定登录TTL。600秒只限制待完成的授权请求，30秒只为中心查询失败重试间隔，都不是accounts登录寿命。刷新pending在网络请求前落盘；中断后不再次使用同一refresh token。该机制保留登录但可能要求重新连接以修复授权凭据，不自动重放刷新。
