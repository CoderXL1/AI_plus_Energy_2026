# 园区高峰用能预警与设备排程助手

项目面向园区充电与用能管理，预测未来 24 小时建筑负荷，识别高负荷时段，并在预约时间、充电位和站内功率约束下安排慢充任务。通过将充电任务移至更合适的时段，在保持任务总能量和按时完成的前提下，降低建筑与充电负荷叠加后的日峰值。

核心流程为 **负荷预测 → 误差情景生成 → 约束排程 → 独立增益筛选**。系统综合考虑平均峰值、不利情景下的峰值和启动时间调整幅度；候选方案通过增益筛选后输出调整建议，否则沿用原排程。

## 实验成果

实验采用 Building Data Genome 2 的三栋办公建筑真实小时级负荷与天气数据，叠加固定种子生成的预约慢充任务。共覆盖 8,955 个案例：441 个基准案例、1,764 个预测扰动案例、6,750 个规模与灵活性案例。扣除 120 个背景观测缺失案例，8,835 个案例进入评分，共评价 46,350 条排程。

| 建筑公开别名 | 完整方法平均日削峰率 | 负向削峰日占比 | 建议输出率 |
| --- | ---: | ---: | ---: |
| Anne | 28.45% | 0.00% | 100.00% |
| Amanda | 0.12% | 0.00% | 3.40% |
| Alice | 2.75% | 2.72% | 93.88% |

削峰率衡量小时平均功率的日峰值相对最早可行排程的变化，均值包含保留原方案的日期。所有评分方案均满足时间窗口、充电位、站内功率与任务能量约束，任务按时完成率为 100%。

独立筛选将负向削峰日占比的建筑平均值从 7.48% 降至 0.91%，建议输出率为 65.76%，体现了收益与调整频率的取舍。对照实验同时揭示了场景差异：Amanda 的上周预测排程平均日削峰率更高，CVaR 与温度响应特征的平均增益因建筑而异。完整比较及 Amanda 零读数诊断见实验报告。

## 未来应用场景

- **办公园区预约充电**：结合员工离场时间和充电需求，生成次日错峰充电计划，供运营人员审核与执行。
- **园区能源管理平台**：接入实时计量和设备状态，展示高负荷时段、可调整任务及预计削峰量，支持运行中的滚动调整。
- **多类柔性设备协同**：在补充设备约束后，将排程对象扩展至储能、蓄冷和可延后运行的设备，协调园区内的用能时序。
- **光伏消纳与需求响应**：引入光伏预测、电价和响应指令，探索就地消纳、用能成本与峰值控制的联合优化。

后续试点将接入真实预约记录、细粒度计量和变压器余量，验证从日前建议到现场执行的效果。

## 项目材料

- [实验报告](reports/实验报告.md)：方法、对照结果、案例分析与应用展望。
- [实验方案与评价口径](experiments/实验方案与口径.md)、[固定实验配置](experiments/config/protocol.json)：样本、参数和评价规则。
- [主实验结果](experiments/results/baseline_summary.csv)、[配对置信区间](experiments/results/paired_confidence_intervals.csv)：分建筑效果与统计比较。
- [逐案例任务与排程](experiments/results/schedule_cases.jsonl)、[完整指标表](experiments/results/all_scheduling_metrics.csv)：每项任务及方案的详细记录。
- [实验覆盖核验](experiments/results/completion_audit.json)、[约束与能量核验](experiments/results/result_audit.json)：实验完整性与方案可行性。
- [数据来源](DATA.md)、[材料导览](PUBLICATION.md)、[AI 辅助使用说明](reports/AI辅助使用记录.md)、[第三方来源与署名](THIRD_PARTY_NOTICES.md)。

## 结果核验与实验复现

### 离线核验

在仓库根目录使用 Python 3.12 运行，仅需标准库：

```sh
python scripts/verify_snapshot.py
```

该入口校验文件 SHA256、案例数量及方法组，并利用逐时真实背景和任务开始时刻，独立复算全部评分方案的时间窗口、容量、能量、峰值、削峰量和启动偏移。额外的实验矩阵与调参预算检查见 `experiments/src/audit_completion.py`，该脚本依赖 pandas，并更新完成审计文件。

### 安装依赖

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

原实验环境为 Python 3.12.14、macOS / arm64，依赖版本见 `requirements-lock.txt`。其他平台需配置 LightGBM 所需的运行库。

### 算法检查与完整重跑

运行 12 项小规模算法检查，覆盖穷举对照、不可行案例、负情景截断、筛选边界和未来信息隔离：

```sh
python scripts/reproduce.py --mode checks --name checks-01
```

完整复现需联网下载约 194 MB 的三个原始 CSV：

```sh
python scripts/reproduce.py --mode full --name full-01 --workers 4
```

运行流程依次为：数据下载与校验 → 算法检查 → 预测训练与特征消融 → 排程调参及全部案例 → 指标与图表生成 → 零读数诊断 → 实验矩阵核验。

每次运行使用独立的 `runs/<name>/` 目录，名称须唯一。结果、图表和日志分别位于该目录下的 `experiments/results/`、`reports/figures/` 和 `run.log`；Markdown 报告单独维护。配置与代码保持一致时，中断的排程可通过运行目录中的 `run_scheduling.py --stage run --workers 4` 续跑，再依次执行 `analyze.py`、`diagnostics.py`、`audit_completion.py`。

数据版本与随机种子固定。限时求解、浮点运算和平台差异可能影响具体启动时刻及耗时，复核以约束满足情况、评价指标和求解状态为准。

## 文件结构

```text
experiments/src/        预测、排程与统计实现
experiments/config/     固定实验协议
experiments/data/raw/   数据来源清单与原始许可
experiments/results/    实验结果快照与文本模型
reports/               实验报告、结果图与 AI 辅助说明
scripts/               离线核验与独立重跑入口
MANIFEST.json           文件内容校验和
requirements-lock.txt  实验依赖版本
runs/                   本地复现输出
```

原始数据由复现入口按固定版本下载，来源、大小与 SHA256 见 `experiments/data/raw/manifest.json`。仓库提供三栋建筑的逐时背景切片、预测及排程结果，便于离线复核；数据署名与许可见 [第三方来源与署名](THIRD_PARTY_NOTICES.md)。
