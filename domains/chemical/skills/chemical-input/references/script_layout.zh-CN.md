# chemical-input 脚本布局

实现按科学操作拆分：

- `scripts/materials/` 负责材料导入、材料合同和名称解析，包括
  `material.py`、`analysis_material.py`、`name_resolution.py`。
- `scripts/reaction/` 负责反应身份、对应关系和与几何无关的准备，包括
  `correspondence.py`、`conformers.py`、`prepare.py`。
- `scripts/geometry/` 负责结构比较编排。
- `scripts/diagnostics/` 负责局部几何观察及其 Job CLI。
- `scripts/tensor/` 负责 Cartesian 张量重排。

`scripts/` 根目录下的文件是现有 Job 和调用方使用的兼容入口，实际执行对应
子目录中的实现，不是第二份实现。新的 executor 应引用分类后的文件，并声明
对应的分类模块路径。
