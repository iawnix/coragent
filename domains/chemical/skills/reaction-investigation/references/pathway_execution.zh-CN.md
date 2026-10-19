# 条件化机制探索与路径检查

只有 R 时保留产物未知。从官能团、质子/电子转移、电荷/自旋、轨道可达性、酸碱/氧化
还原条件、几何、溶剂/催化剂参与，以及区域/立体/构象竞争提出可证伪假设，明确候选数
和 Job 预算。不能把熟悉的反应名模板当作机制。给定 R/P 时先判断是否需要中间体，
再选择 QST2/3。分离片段需构象/复合物准备，已给复合物保留相对取向；按需要优化并
表征候选势阱。扫描或 IRC 发现中间体/意外出口时扩展路径；自旋变化使用专用交叉证据。

上一轮计算虽未得到鞍点但提供了振动、梯度、路径或电子结构线索时，可将这些线索整理为
编辑假设，交给 [reactive-geometry](../../reactive-geometry/SKILL.zh-CN.md) 生成新的反应中心取向和局部位移候选；候选仍需独立
预优化、TS 优化、频率和 IRC 验证。

chemical.pathway-check@1 使用 structure 环境、input 角色、chemical-pathway-input/1，
检查明确材料、假设和证据关系，不修改 Node，也不自动宣告用户任务完成。

输入字段：

- species：1–128 个 ID，各有 material、origin。origin 包含 kind
  （provided/hypothesis/calculated）、source_sha256；猜测物种还需 hypothesis_id。
  未解析名称需先成为明确结构，才能进行原子记账。
- hypotheses：1–64 个 ID，各有 statement、falsifier、source_sha256。
- reactants、可选 products：物种→正整数计量；products=null 保留 R-only 的未决目标。
- budget：max_jobs、max_candidates，均为 1–10000；unexplored 列出未探索问题，
  可为空。它们是研究预算声明，不是自动机制生成器或自动派发循环。
- steps：最多 256 条，包含 id、hypothesis_id、kind（elementary/unresolved/crossing）、
  reactants、products、mapping、observations、可选 validation。
  每侧总系数 ≤8，展开状态最多 1024 原子。
- mapping：完整的对应对列表，每端为 [物种 ID, 从零开始的实例序号, 本地 atom_id]。
  实例编号处理重复计量。检查元素/同位素对应、原子与电荷守恒；缺映射保持 incomplete，
  不自动虚构原子对应。
- observations：source_sha256、interpretation（supports/conflicts/unresolved）、note。
  初始猜测、实际观察、冲突和未探索内容分别保留。
- routes：最多 64 个命名步骤 ID 序列。共享中间体和旁观物种计量必须完全一致；
  缺步骤、断裂关系、未知产物和未达到目标都形成明确 gaps。

可选的基元步骤 validation 包含 saddle_material、saddle_evidence、mode_coordinates、
两个 paths，采用已有通用模式/IRC 合同。程序以路径内确切端点材料重新执行检查，
不接受调用者提供的 pass 布尔值。目前该整合要求每侧是一个完整材料；分离反应物
提供 IRC 势阱证据前需显式关联为端点材料。crossing/unresolved 步骤保留未评估，
应另用相应物理证据。

输出分别记录计量、映射、声明态连续性、观察、重算步骤证据和路径缺口。
不通过多重度相加推断片段自旋耦合。supported_within_scope 表示提供的经典步骤
检查及端点连续性通过，不表示穷尽机制、动力学优势或原始研究任务已交付。

同一科学问题的尝试继续使用同一 Node。保存负结果、收集失败 Job；改变方法前核对
回执，等待/上下文恢复后读取持久 Task/Node/Artifact，不重复派发未知 Job。
分别报告热力学排序、条件动力学预测和未探索分支。只有独立科学问题才拆 Node；
两步化学反应不自动等于两个研究 Node。
