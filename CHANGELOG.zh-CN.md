# 变更日志

这里记录面向用户的变化；当前设计见[架构文档](docs/ARCHITECTURE.zh-CN.md)，旧方案可通过 Git 历史查询。

## 未发布

- 为 CoRHub 0.20.0+64 增加经认证的 Host `files/list`、`files/stat`、`files/read` 和
  `files/pin`：通过既有 Link 有界浏览材料、按版本固定文件快照，不唤醒 Pi 或暴露状态文件。

- **0.19.0 不兼容更名**：产品及仓库统一为 CoRAgent / `coragent`。命令、包、服务、
  安装标识和环境变量统一新名称，不提供旧别名或回退；Python 内部导入仍为 `research_agent`。
- Host / Relay 改用 `coragent-host/2`、`coragent-link.v1`、`cah_` 和 `cad_`。

- 固定 Pi 运行时与 SDK 更新到 1.1.0，保留协议 8 和请求准入，并使用新的上下文 API 与 token 估算器。
- 研究工具卡片展示已记录的执行耗时，重连后仍保留；Job 提交耗时与后台计算时长分开。
- 增加通用化学材料、映射/构象比较、CREST 集合、复合物采样、xTB/Gaussian 扫描与
  NumPy NEB、QST2/QST3 准备，以及不依赖反应名称的驻点/模式/IRC 检查。
- 增加热化学与构象自由能、多步路径检查、条件 TST/竞争分支和质量作用动力学网络。
- 增加有限范围的 Gaussian TD/TDA 计算、给定张量的态跟踪，以及不同自旋表面的局部
  交叉搜索和独立数值检查。确定性验收不替代真实求解器科学基准，见[能力清单](domains/chemical/skills/method-selection/references/capabilities.zh-CN.md)。
- 改进终端 slash 补全、焦点/草稿保留、字段语义配色、系统提示词渲染及 Monitor 的任务/连接状态展示。
- 从受支持的 package surface 移除已退役的 ordinary-Pi runtime；Native Pi Harness 是唯一
  运行时入口。
- 明确 Research Memory、有界 turn context、capability catalog 和 Monitor 唤醒边界。
- 增加仓库治理文档与自动化 Skill contract 检查。
- 为项目拥有的源码加入 Apache-2.0 许可证及 SPDX 元数据。

本条目还没有对应的发布 tag。发布说明必须包含 package 版本、固定的 Pi revision、迁移说明
以及运行过的测试 lane。
