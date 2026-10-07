# 园区用能预警与设备排程：可复现实验

这是面向技术评审的脱敏实验仓库。任务是使用历史建筑负荷与天气预测未来 24 小时背景功率，再对预约慢充任务进行约束排程，评价日峰值变化。

**真实背景数据 + 仿真充电任务**：本项目不是现场设备试验，削峰率不能解释为节能率、实际电费降幅或 15 分钟计费需量改善。

## 评审入口

- [实验报告](reports/实验报告.md)：方法、对照、消融、置信区间、规模与扰动实验、失败案例和局限。
- [固定实验协议](experiments/config/protocol.json)及[实验口径](experiments/实验方案与口径.md)。
- [主实验结果](experiments/results/baseline_summary.csv)、[配对置信区间](experiments/results/paired_confidence_intervals.csv)。
- [全部逐案例任务与排程](experiments/results/schedule_cases.jsonl)、[完整指标表](experiments/results/all_scheduling_metrics.csv)。
- [完成情况审计](experiments/results/completion_audit.json)、[约束与能量审计](experiments/results/result_audit.json)。
- [数据来源与署名](DATA.md)、[公开版整理说明](PUBLICATION.md)、[AI 辅助使用记录](reports/AI辅助使用记录.md)。

## 主要结果

共处理 8,955 个案例：441 个基准案例、1,764 个预测扰动案例、6,750 个规模与灵活性案例。其中 120 个因真实背景缺失排除；8,835 个进入评分，共 46,350 条排程评价。

| 建筑公开别名 | 完整方法平均日削峰率 | 负向削峰日占比 | 建议输出率 |
| --- | ---: | ---: | ---: |
| Anne | 28.45% | 0.00% | 100.00% |
| Amanda | 0.12% | 0.00% | 3.40% |
| Alice | 2.75% | 2.72% | 93.88% |

所有评分方案的约束违反次数为 0，任务能量偏差为 0。完整方法并非普遍优于简单方法：CVaR 和温度响应特征未显示跨建筑稳定平均增益，筛选会牺牲部分收益。Amanda 测试期包含大量零读数，报告保留了主结果及单独的事后诊断。

## 1. 无需下载数据的结果核验

在仓库根目录使用 Python 3.12 运行，**仅用标准库，不需要安装科学计算依赖**：

```sh
python scripts/verify_snapshot.py
```

该入口只读已有结果，不反序列化 pickle、不训练或调用求解器。它校验文件清单的 SHA256、案例数量及方法组，并用提交的逐时真实背景和开始时刻独立复算全部评分方案的时间窗口、容量、能量、峰值、削峰量和启动偏移。

核验提交结果不等于独立重做全部实验。完整矩阵和调参搜索预算的额外检查见 `experiments/src/audit_completion.py`；它需要 pandas，会重新写入同内容的完成审计文件。

## 2. 安装实验依赖

```sh
python -m venv .venv
```

macOS / Linux：

```sh
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
```

Windows PowerShell：

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-lock.txt
```

锁定文件记录原实验使用的版本。原实验为 Python 3.12.14、macOS / arm64；其他平台需满足 LightGBM 的平台运行库要求。仓库不包含虚拟环境或本机库路径。

## 3. 算法检查与完整重跑

先运行 12 项小规模算法检查，包含穷举对照、不可行案例、负情景截断、筛选边界和未来信息隔离：

```sh
python scripts/reproduce.py --mode checks --name checks-01
```

完整复现（需要联网下载约 194 MB 的三个原始 CSV）：

```sh
python scripts/reproduce.py --mode full --name full-01 --workers 4
```

每次运行写入独立的 `runs/<name>/`，不覆盖提交的 `experiments/results/`。同名运行目录存在时拒绝覆盖，请换一个名称。入口依次执行：固定版本下载与校验 → 算法检查 → 预测训练与消融 → 排程调参及全部案例 → 指标、图表及方案复核 → 零读数诊断 → 实验矩阵审计。终端输出同时保存在运行目录的 `run.log`。

完成后，结果位于 `runs/full-01/experiments/results/`，图表位于 `runs/full-01/reports/figures/`。该入口生成科学实验结果与图表，不自动改写仓库中的评审报告。中断后，可在确认配置和代码未改变的前提下，直接使用对应运行目录中的 `run_scheduling.py --stage run --workers 4` 继续未完成排程，然后依次运行该目录中的 `analyze.py`、`diagnostics.py`、`audit_completion.py`。

随机种子和数据版本已固定，但 2 秒墙钟求解预算、浮点运算、平台与求解器差异可能导致可行解或耗时不同。请比较约束、指标和求解状态，不承诺每个开始时刻或计时值逐字节一致。

## 数据与文件安排

原始数据不直接提交；固定版本、来源 URL、大小和 SHA256 保存在 `experiments/data/raw/manifest.json`，下载入口会核验。已提交的逐时结果含三栋公开别名建筑的背景观测切片，便于离线复核，因此本仓库仍包含公开数据的派生内容；署名和原始许可一并保留。

不附带申报书、个人姓名或联系方式、原始 Word/PDF、聊天记录、绝对本机路径、虚拟环境、运行日志及 pickle 缓存。LightGBM 文本模型可供审查；线性模型和排程中间上下文由完整重跑重新生成。

```text
experiments/src/        科学实验实现
experiments/config/     固定实验协议
experiments/data/raw/   来源清单与原始许可（不含原始 CSV）
experiments/results/    提交的结果快照与文本模型
reports/               Markdown 报告、结果图与 AI 辅助说明
scripts/               离线结果核验、隔离重跑入口
MANIFEST.json           公开文件的内容校验和
requirements-lock.txt  原实验依赖版本
runs/                   本地重跑输出（自动忽略，不提交）
```

第三方数据条款见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。本仓库整理未为原创代码新增开源许可，也不将第三方数据许可套用于全部代码。
