# R2a测试证明契约0.1

日期：2026-10-27。状态：仅合成实验，尚非正式签发或授权协议。规范为[证明Schema](trust-proof-v0.1.schema.json)和[测试信任Schema](test-trust-v0.1.schema.json)，探针位于experiments/scripts，不接入平台或机器人。

## 三类证明

共同字段含schema_version、kind、issuer、deployment_id、data_kind=synthetic、binding、issued_at和body。binding同时绑定场景、发布、真值、视图身份及摘要，运行包清单原字节摘要、profile和scope摘要。这里binding.package_sha256指agent-package.json摘要；它不同于R0 source.package_sha256所指的上游合成服务包清单摘要。

| kind | body内容 | 必须的签发角色 |
|---|---|---|
| content_statement | package_schema | publisher |
| capability_grant | audience、能力列表、策略摘要、绑定状态epoch/sequence及payload摘要、起止时间、离线限额 | validity |
| status_snapshot | epoch/sequence、audience、期限、能力完整列表及状态/原因；可选challenge | validity |

整数时间为UTC Unix秒；测试值不代表现场有效期。Schema限制整数、数组、枚举及未知字段；探针补充时间区间顺序、状态能力名唯一、预期来源/角色/受众相等检查。它不读取可信时钟，不判断当前是否过期，也不判断状态是否比本机记录更新。

状态摘要使用验签后payload原始UTF-8字节的SHA-256，不能对同一JSON对象换空白重算后声称原摘要不变。grant与status的交叉一致性、高水位、撤回、epoch权限和时间判断留待R2b；本轮不以状态引用字段存在就声称已经建立授权链。

## JWS与受限解析

采用JWS Compact三段。protected必须且仅含alg=EdDSA、typ=cospace-test-proof+jws、kid及version=0.1。限定Ed25519的32字节公钥和64字节签名，不接受none、算法替换、jku/x5u、crit或其他未支持头字段。base64url必须无填充且规范编码。

先解析有界protected从调用方显式测试信任配置选钥，验签原始编码的protected.payload，再解析payload。token最多49152字符，单段JSON最多32768字节，嵌套最多12层，能力数组最多16；重复JSON键、非法UTF-8及不受支持的Schema拒绝。校验器不访问网络，也不从消息取公钥。

测试信任配置明确test_only=true、部署及最多16个kid；每项仅含公钥、issuer和角色。重复kid拒绝。此配置由调用方显式提供，未实现根签名、委托、信任版本、密钥过期或撤销；不能把它作为生产信任根。

## 结果与运行范围

成功结果为proof_verified=true、authorized=false、robot_ready=false，并列出not_checked。签名和固定绑定通过仅说明此测试证明由所给测试公钥签发，不代表能力获准使用。

Node原生crypto只作实验密码桥接，Python处理Schema和领域约束；私钥测试seed仅在测试进程及子进程stdin内存中使用。仓库中的RFC公开标准seed不作设备凭据；其他随机私钥不落盘。该桥接不进入C++ SDK或生产Python依赖，不新增生产Node运行要求。

现有R0/R1接口仍保留unverified_sample_only。新测试证明不改变包格式、激活和会话门禁；正式可信特性必须经新契约及兼容门禁接入，不能由现有CLI隐式提升。
