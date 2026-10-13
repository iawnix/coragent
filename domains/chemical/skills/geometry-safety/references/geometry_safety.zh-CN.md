# 几何安全检查合同

检查器返回符合 `chemical-geometry-safety/1` 的 JSON。硬检查范围是有限笛卡尔坐标、原子身份/顺序、
原子核塌陷，以及显式反应原子对之外的严重短接触。它不从坐标推断键，也不认证过渡态。

`bonded_pairs` 和 `reaction_pairs` 使用从零开始的原子索引。反应原子对可以比正常键更长或更短，
但仍不能低于绝对塌陷下限。非反应非键接触使用元素相关的共价半径比例检查。反应中心非平衡警告
对许多有效 TS 候选都是预期结果。

独立执行器接受如下输入：

```json
{
  "schema_version": "chemical-geometry-safety-input/1",
  "elements": ["C", "C"],
  "coordinates": [[0, 0, 0], [1.8, 0, 0]],
  "bonded_pairs": [],
  "reaction_pairs": [[0, 1]],
  "profile": "ts_candidate"
}
```

输出一个 JSON 结果。Gaussian 集成使用同一解析器，在启动可执行文件前检查所有显式坐标块。路径
合同也使用同一几何函数检查端点和每个 NEB image。
