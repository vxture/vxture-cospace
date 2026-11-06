# 产品模块

当前建立spatial、service及data、ontology两个支撑平台的边界。其余construction、views/human、views/agent、lifecycle、adapters与infrastructure按[目录基线](../docs/architecture/项目目录结构设计-v0.1.md)随实现增加。

spatial承载真值领域基础；service消费固定版本组合。应用装配具体文件、存储和运行实现，避免领域模块与数据库、ROS消息或算法内部类绑定。

各模块公开边界、语言内包布局及构建目标随技术栈设计确定；当前README不代表可安装或可运行的软件包。
