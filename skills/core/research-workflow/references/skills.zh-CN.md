# Skill 资源

Pi 加载已安装 Skill 描述，Agent 按需读取 SKILL.md。CoRAgent 校验安装资源摘要。读取 Pi 提供的真实 Skill 路径，相对引用从该目录解析。

使用列出的准确资源名。引用不存在时检查当前 Skill 的 references 列表，不根据主题猜目录。

参数错误或路径缺失是可修复的局部错误，阅读说明修正后重试，不能因此判断整个研究无法完成。软件失败与反驳科学假设的证据需要区分。

默认发现入口为英文 `SKILL.md`；`SKILL.zh-CN.md` 是中文对照，不会按用户语言自动替换入口。需要时可显式读取中文文件，回复语言仍遵循用户要求。

TRI 服务部署、节点/资源配置或调度故障排查参阅 [TRI 部署文档](../../../../docs/TRI_OPERATIONS.zh-CN.md)。研究计算继续通过选定执行目标和 Job 工作流执行。

TRI、PBS、Torque 或 Slurm 的资源选择、目标配置和队列诊断使用 [batch-schedulers](../../batch-schedulers/SKILL.zh-CN.md)。
