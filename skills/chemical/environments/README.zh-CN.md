# 化学执行环境

[English](README.md)

这些资源供安装使用，与 Host 控制环境分离。Conda 显式锁为每个包固定 SHA-256，
目标为 Linux x86_64。`wrapper.lock` 要求 glibc >=2.17，科学与渲染锁要求
glibc >=2.28。CF22D 选择通用 x86_64 PySCF 构建，不绑定维护者的 CPU。
其他目标需要单独核验适合该目标的锁文件。

| 锁文件 | 绑定 | 内容 |
| --- | --- | --- |
| wrapper.lock | Gaussian/xTB/CREST 包装脚本 | Python 3.11 与安装工具；原生求解器单独安装 |
| structure.lock | structure、validation | RDKit、NumPy、Matplotlib、Pillow，供结构/轨迹/报告分析 |
| path.lock | path_xtb、path_gaussian | structure 依赖加 ASE 3.29.0 与 SciPy，供 NEB v2 |
| cf22d.lock | pyscf | PySCF、geomeTRIC 和 dispersion，全部由 Conda 安装 |
| render.lock + render.requirements.txt | render | RDKit、Cairo、Matplotlib、xyzrender 及其依赖 |

基础文本报告 helper 使用 Host 标准库；图文报告/轨迹 Job 使用 structure，均不需要渲染锁。渲染环境中的 notebook 依赖来自
xyzrender 上游要求，只安装在渲染目标中。这些环境均不安装 CoRAgent wheel。

在执行机器上独立准备这些环境，再将 Python 前缀、锁文件和原生求解器的绝对路径
绑定到 `config.toml` 中平台或调度入口的 `bindings`。主安装器校验已配置绑定；
未配置时不创建科学环境，也不创建 Qrun 队列。

目标机器上的安装工具使用显式绑定：

```bash
python3 -B packaging/coragent_packaging/installer/install_job_environment.py \
  --config /absolute/job.toml --platform PLATFORM --scheduler-entry ENTRY --backend structure
```

在执行机器上运行，所有路径属于该机器，本机控制端的 Python 路径不能当作远端环境。
`wrapper` 为已配置的 Gaussian/xTB/CREST 包装脚本提供 Python，原生求解器仍单独安装。
使用专用、版本化的前缀。该工具保存核验后的归属与包清单，不负责 CoRAgent 版本切换，
也不提交验收 Job。structure 与 validation 可共用前缀；CF22D 不需要自定义激活脚本
或 `LD_PRELOAD` 补丁。

主配置是唯一维护入口，`generated/job.toml` 只是生成输入。在线 PubChem/OPSIN 查询可选，
安装器不会默认启用。显式设置 `[name_resolver]`，再在 structure 后端环境中绑定
`CORAGENT_NAME_RESOLVER_CONFIG`，路径必须能被所选平台读取。本地结构准备可交给远端计算，
不要求每个平台都启用名称查询；已有结构输入不要求该服务。

structure 验收检查 RDKit 和结构生成，不要求解析器配置。安装时通过
`--verify-job-target PLATFORM/ENTRY` 显式请求有时限的验收 Job。报告区分环境检查
与实际执行，离线验收不访问外部名称服务。

安装时不重新求解依赖。固定的 pip 产物下载到环境父目录下的缓存，再以
`--require-hashes`、`--no-deps` 安装，并用 `pip check` 检查依赖完整性。
目标端工具的 `--package-cache` 可指定产物目录；`--offline` 仅使用该目录与 Conda 缓存
（`CONDA_PKGS_DIRS`）。锁与发行文件保持只读。新建安装中断后删除该次创建的前缀，
已有前缀不就地更新。显式 `--adopt` 才会核验预先准备的环境并发布安装回执。

绑定配置完成后，用已安装的控制解释器执行
`-m research_agent.application.environment_check --config /absolute/job.toml`，核验实际目标与声明的
依赖导入，包括 SSH 目标。随后运行有时限的科学 Job；包清单和导入一致不代表方法
已经有效工作。

更新锁时，在隔离环境中以 `CONDA_OVERRIDE_ARCHSPEC=x86_64` 从 conda-forge 求解
记录的根依赖，使用 `conda list --explicit --sha256` 导出，并在全新安装及实际计算
通过后发布。pip 条目必须附上游产物的摘要。不要导出凭据、引入仅本机存在的 wheel，
或就地替换正在使用的安装锁。

可选 `path` profile 为显式配置的 `path_xtb` / `path_gaussian` 原生绑定使用
path.lock，提供 RDKit/NumPy、ASE、SciPy，供扫描、梯度与 ASE NEB v2，不改变旧轻量包装器。
例如为 `[execution.platforms.local.bindings.path_xtb]` 配置
`command = "/opt/xtb/bin/xtb"`（需要时加 activation_script），绑定基于 `path.lock`
准备的前缀，再用目标端工具安装该后端。该 profile 不默认进行原生科学计算冒烟测试；
选定入口的环境检查与显式有界科学 Job 需要分别验收。

Gaussian 数值解析还使用固定版本 cclib 1.8.1：wrapper、structure、path 配套的 `.requirements.txt` 包含锁定哈希的依赖；wrapper/structure 补充 SciPy。更新需创建新的不可变环境，不能直接覆盖正在运行的环境。cclib 只提取数值，不决定优化阶段、IRC 完整性或化学连通性。
