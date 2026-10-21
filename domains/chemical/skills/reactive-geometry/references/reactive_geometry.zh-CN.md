# 反应构象输入合同

[English](reactive_geometry.md)

## 内容

- [输入](#输入)
- [编辑操作](#编辑操作)
- [检查、输出与交接](#检查输出与交接)

`chemical.reactive-geometry@1` 使用 `structure` 绑定（RDKit/NumPy），只编辑坐标。
受限预优化和 TS 搜索使用独立求解器 Job。

## 输入

### Agent 工具选择

当需要把显式映射键变化转换成固定/移动角色和局部接近假设时，使用
`chemical.reactive-sites@1`；使用 `chemical.reactive-pose@1` 采样这些假设；在 QST 或 NEB
之前，用单点 `chemical.scan-xtb@1` 执行约束预优化。[能力地图](capability_map.zh-CN.md)、
[调用卡片](call_cards.zh-CN.md)和[恢复手册](recovery_playbook.zh-CN.md)说明如何解释和组合
这些结果；它们都不会把几何结构直接判定为 TS。

### 自动生成片段取向

`chemical.reactive-pose@1` 接受 `chemical-reactive-pose/1`。请求中的 `material`
必须嵌入 `chemical-material/1` 对象：

```json
{
  "schema_version": "chemical-reactive-pose/1",
  "material": {"schema_version": "chemical-material/1"},
  "bond_changes": [{"atoms": ["C", "F"], "before": 0, "after": 1}],
  "sampling": {"count": 32, "direction_count": 7, "cone_degrees": 35}
}
```

至少一个声明的成键必须连接图中的独立片段。执行器将较大片段作为固定参考，使另一片段的
局部反应原子朝向固定原子，并采样距离和扭转角。多接触取向会对移动片段执行刚性拟合；
拟合残差超过 `pair_tolerance` 的候选会被拒绝。`seed` 使有界采样可复现；`distances`
可按成键对覆盖基于共价半径生成的默认距离，`twists` 默认是 `[0, 120, -120]` 度。

结果会记录局部方向、刚性变换、反应对距离和几何安全报告。执行器不嵌入 SMILES、不排序
电子能量，也不声称取向是 TS。先使用 `chemical.seed` 或 CREST，再审查取向集合，随后分别
运行受限预优化、QST、扫描或 NEB。

`chemical-reactive-geometry/1` 包含嵌入的 `material`（2–256 原子、Å 坐标）、
`bond_changes`、`edit_hypotheses`，以及可选 `sampling`，不要求产物。
先通过 material-preparation/CREST 导入或组装材料；本执行器不嵌入 SMILES、不优化单体。

材料需要参考分子图。对没有当前图的 TS/路径候选，提供 `reference_material`，其原子
ID、顺序、元素/同位素和态声明必须相同。参考图只定义受保护键和片段，不认证当前几何
连通性；独立材料先显式映射、重排。`before` 键级必须与参考图一致，`after` 必须不同。
声明的反应键可以拉伸，其他键均相对源几何检查长度变化。

每个假设包含 `id`、`note`、`source_refs`（初始化学假设可为空）、`operations` 和
可选的最终 `checks`。证据使用已收集 Artifact ID；字符串归因不替代 Job 的 input-artifact
绑定。下面从完整 material 文件生成请求，假定其中 ID 为 C、Cl、F 及显式 H：

```python
import json
material = json.load(open("material.json"))
spec = {
    "schema_version": "chemical-reactive-geometry/1", "material": material,
    "bond_changes": [
        {"atoms": ["C", "F"], "before": 0, "after": 1},
        {"atoms": ["C", "Cl"], "before": 1, "after": 0}],
    "edit_hypotheses": [{"id": "backside", "note": "检验 C-Cl 反方向的进攻假设",
        "source_refs": [], "operations": [{"kind": "place", "atoms": ["C", "F"],
            "mobile_atoms": ["F"], "direction": {"kind": "away", "atoms": ["C", "Cl"]},
            "values": [2.4, 2.6], "cone_degrees": 15}],
        "checks": [{"atoms": ["Cl", "C", "F"], "minimum": 150, "maximum": 180}]}],
    "sampling": {"count": 16, "seed": 0}}
json.dump(spec, open("edits.json", "w"), indent=2)
```

示例距离只是待检验假设，不是通用 TS 键长。

## 编辑操作

| kind | 字段与行为 |
| --- | --- |
| `place` | `atoms: [固定原子,移动原子]`；`mobile_atoms` 是一个完整的独立参考片段；`values` 为距离，必填 `direction`，可选 `mobile_direction`、`twists`（角度，默认 `[0]`）、`cone_degrees`（默认 0，最多 90）。原子对必须声明为新成键。 |
| `distance` | 两个 `atoms`，`mobile_atoms` 含第二原子、不含第一原子，`values` 为距离；沿现有轴平移整个选定原子组。 |
| `angle` | 三个 `atoms`，中间原子为支点，移动第三原子及其组、固定前面的锚点；`values` 严格位于 0–180 度。 |
| `dihedral` | 四个 `atoms`，第四原子及其组绕第二—第三原子轴旋转；`values` 为 -180–180 度。若环内编辑拉坏其他键，会被拒绝。 |
| `displace` | 完整 `atom_ids`、精确的规范化 `material_sha256`、N×3 `vectors`、`representation: "cartesian_direction"`、已列于假设的 `source_ref`，以及带符号的 Å 振幅 `values`。 |

摆放方向可由局部坐标系定义：`{"kind":"away","atoms":[中心,邻居,...]}` 指向远离
邻居质心的方向；`{"kind":"normal","atoms":[中心,邻居1,邻居2]}` 是平面法向；
`{"kind":"vector","vector":[x,y,z]}` 是源笛卡尔轴上的显式向量。局部坐标系可用
`sign: -1` 选择反方向/反面。固定坐标系必须位于移动组之外，移动坐标系必须属于该组。
`mobile_direction` 通过纯旋转对准固定中心，twists 探索绕接近轴的旋转。这些是几何假设，
不是求解器计算的轨道方向。

模式向量保留相对幅度和零向量。应对**整个模式**使用同一个缩放系数，使最大原子向量模
不超过 1；此时振幅给出单原子位移的上限。不能直接传入梯度或质量加权模式。选用与
计算相同的几何与坐标轴；材料摘要能绑定几何和顺序，不能证明张量坐标轴正确。
规范化摘要为 UTF-8 JSON（`sort_keys=True`、`separators=(",", ":")`、
`ensure_ascii=False`、`allow_nan=False`）的 SHA256，前缀 `sha256:`。

每个候选都从源几何重新开始，操作顺序执行。values/twists 采用笛卡尔积，各假设轮流
取样；非零 cone 允许固定随机种子的方向扰动。`count` 限制总尝试数（1–256），不是
通过数；不会无限重试，全部被拒绝也是有效的失败记录。

## 检查、输出与交接

每个编辑目标都在最终几何上重新测量，`tolerance` 默认 0.03 Å / 3 度。
摆放还复核接近方向和可选移动坐标轴，`direction_tolerance_degrees` 默认 3 度。
可选 `checks` 提供 2/3/4 个原子 ID 和有序的 minimum/maximum；跨越 ±180 度的区间
拆成不同假设。多个摆放操作顺序执行，不是同时求解所有约束；不相容的多接触目标会被
拒绝，需要修改假设或使用求解器受限优化。

所有原子对都检查塌陷，非键接触使用共价半径和 `clash_scale`（默认 .85）。
非反应键相对源几何最多变化 `protected_bond_tolerance`（默认 .15 Å）。
反应中心之外、参考图已声明的四面体手性检查是否保持源几何的朝向，不等于完整立体身份验证。
`max_local_displacement`（默认 .75 Å）限制每原子累积的局部编辑；刚性组装的整体
位移不受这个上限约束。它不是能量或梯度判据。

输出包含 input.json、result.json 和通过/拒绝候选的 XYZ。通过候选还输出可复用的
material.json：当前连通性保持未指定，参考图/map 标签保存在 derivation 中，重复编辑也继续保留；电荷、态
声明和局部原子 ID 保留。来源引用、实际变换、检查和拒绝原因均随结果保存。
排序只依据归一化的几何目标误差，不偏向最低能势阱、不估计能垒。重复坐标单独报告。
全部被拒绝时非零退出，但保留报告。enumeration_complete 只表示有限配置的尝试已遍历，
不表示构象空间被穷尽。

```text
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --executor chemical.reactive-geometry --version 1 --input input=<work_dir>/edits.json --input-artifact <source-ref> --output <work_dir>/edit-request.json
```

使用 research_create/read 返回的 work_dir 绝对路径。将 request_file/request_sha256
和 node_id 交给 job_start；终止后 job_collect，同时收集拒绝和失败结果。审阅候选后按需
运行独立的受限预优化 Job，复核约束以及能量/梯度证据，显式保持相容的设置与求解器输入；
本执行器自身不启动预优化。候选可交给 chemical.qst-prepare（QST3 需完整 guess_mapping）、
扫描或显式准备的 ASE images；单个候选不能补齐缺失的 NEB 端点。
