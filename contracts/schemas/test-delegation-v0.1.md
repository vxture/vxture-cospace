# 测试根委托契约 0.1

日期：2026-10-27。仅用于合成实验，不是生产信任配置或机器人授权格式。

[Schema](test-delegation-v0.1.schema.json)限定单层委托：部署、外部指定版本和最多16个子密钥；各子密钥声明kid、issuer、公钥、publisher/validity角色、场景范围、有效期及撤回标志。重复kid和空时间区间拒绝。

使用JWS Compact，受保护头仅允许alg=EdDSA、typ=cospace-test-delegation+jws、kid及version=0.1。原始header.payload字节由预配Ed25519测试根验签；消息不得携带或替换根。版本必须与调用方外部指定的expected_version完全相等，部署同样严格匹配。没有远程密钥获取或隐式版本升级。

加载器位于experiments/scripts/delegation_probe.py。委托限制由实验ValidityStore执行，三类证明的签发时间及查询有效区间必须同时满足策略与签名子密钥约束。信任配置摘要绑定状态库；变更配置时拒绝重开，不自动迁移。

根轮换、根自身有效期管理、多层链、信任版本高水位、在线撤回与设备恢复尚未实现。测试公钥和签名证书可保存；随机私钥只驻留试验进程内存。
