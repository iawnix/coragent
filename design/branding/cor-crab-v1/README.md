# CoR 螃蟹标志优化提案 v1

基于 CoRHub 前身的 PNG 螃蟹角色重新绘制的矢量设计源。主标志已用于 [CoRAgent Web](../../../components/coragent-web/static/logo.svg)，并以相同 SVG 保存到 [README 随包资源](../../../assets/branding/coragent.svg)。本目录保留设计源和对照展示；移动端资源的实际接入状态以 CoRHub 仓库为准。

## 设计方向

- 保留青蓝双钳、三角形折面身体、黑色双眼和顶部金环。
- 双钳、手臂与主体采用对称几何；放大钳口的留白，统一轮廓节奏。
- 用简洁渐变及少量折面保留原有立体感，去除原图细碎纹理和重高光。
- 金环保留为品牌记忆点，不强行增加字母、分子、网络节点等新符号。
- CoRAgent 与 CoRHub 共用图形，以字标区分；应用图标内不放文字。
- 小尺寸版取消眼睛高光与底部细分折面；单色版使用轮廓及眼睛镂空。

## 文件

| 文件 | 用途 |
| --- | --- |
| `cor-brand-proposal.png` | 原版对照、品牌组合、深浅背景和小尺寸展示 |
| `cor-crab-mark.svg` / `.png` | 彩色透明底主标志 |
| `cor-crab-small.svg` / `.png` | 小尺寸简化标志，建议用于 16–32 px 场景 |
| `cor-crab-mono.svg` / `.png` | 单色标志；SVG 可修改根元素 color |
| `corhub-icon.svg` / `.png` | 1024 × 1024 方形浅底应用图标设计源，交由平台施加圆角 |
| `generate.py` | 本地可重复运行的矢量与展示图生成脚本 |

PNG 主资产均为 1024 × 1024。标志画布留白用于应用图标安全区域；紧凑字标组合可根据可见轮廓调整间距。

配色：青绿 `#10BDBB`、研究蓝 `#1479ED`、金环 `#F7BC2A`、深海蓝 `#102C42`。渐变使用同色系的明暗色阶。

展示图使用本机 Noto Sans CJK 和 Red Hat Display 字体；当前字标仅是排版方向，尚未转曲或形成独立字标资产。

## 复现

在本仓库根目录执行（需要下述本地环境与原图仓库）：

```sh
local_debug/brand-design/venv/bin/python design/branding/cor-crab-v1/generate.py
```

依赖为 CairoSVG 和 Pillow，环境位于本机私有 `local_debug/brand-design/`；该目录不是交付物。生成器从同级 `ts-phone` 仓库读取当前原图，仅用于对照展示。

本仓库未记录 Android/iOS 启动器实机验收。更新主标志时需同步 Web 与 README 的 SVG 副本；README 资源置于 `assets/`，随 Agent 安装包分发。
