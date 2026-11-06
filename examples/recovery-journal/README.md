# 恢复日志结构样例

records.json包含intent、commit_receipt、recovery_plan、recovery_result四种合成记录。用于设计讨论及Schema核对，不能导入现有门禁或作为提交/恢复凭据。

token采用占位JWS `e30.e30.AA`，没有合法签名；身份和状态摘要是格式占位值，未与真实状态建立关系。样例中的reconciled仅用于枚举展示，authorized与robot_ready仍固定false。

从仓库根目录执行`.venv/Scripts/python.exe -m experiments.scripts.check_recovery_contract`可核对样例与结构负例；该工具不验证恢复协议的行为。规范见[契约](../../contracts/schemas/recovery-journal-v0.1.md)。
