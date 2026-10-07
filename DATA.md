# 数据来源与实验样本

项目使用 Building Data Genome Project 2（BDG2）的公开建筑电表、天气和元数据，覆盖 2016 至 2017 年。建筑历史负荷构成实验背景，预约慢充任务由固定种子的程序生成。

- 数据仓库：[Building Data Genome Project 2](https://github.com/buds-lab/building-data-genome-project-2)。
- 固定版本：`9b97ccbe90096aff42ed4fd6493bf7ae692d7118`。
- 数据文献：Miller C, Kathirgamanathan A, Picchetti B, et al. *The Building Data Genome Project 2, energy meter data from the ASHRAE Great Energy Predictor III competition*. Scientific Data, 2020, 7: 368. DOI: 10.1038/s41597-020-00712-x.

## 样本选择与处理

从办公楼中按训练期有效率、正值率及天气完整度筛选，再按公开编号排序，每个站点取第一栋合格建筑，最终选取前三个站点。三栋建筑的公开别名为 `Bull_office_Anne`、`Eagle_office_Amanda` 和 `Fox_office_Alice`，用于关联来源、模型与实验结果。

负值视为缺失；历史输入前向填补，评分标签保留原始观测。排程评价使用完整的 24 小时背景，120 个缺失背景案例保留排除记录。零读数按固定规则纳入主实验，并通过事后分组诊断分析其影响。

## 数据材料

| 材料 | 内容与用途 |
| --- | --- |
| [原始数据清单](experiments/data/raw/manifest.json) | 固定下载地址、文件大小与 SHA256 |
| `experiments/results/*_forecasts.csv` | 三栋建筑的逐时背景观测与预测 |
| [选样记录](experiments/results/selection_audit.csv) | 候选建筑质量统计与选中标志 |
| [逐案例排程](experiments/results/schedule_cases.jsonl) | 仿真任务、启动时刻、求解状态与指标 |
| [数据许可](experiments/data/raw/LICENSE) | 上游数据许可原文 |

完整复现入口自动下载电表数据约 174 MB、天气数据约 19 MB、建筑元数据约 0.27 MB，并校验文件内容。选样复现使用完整公开输入，下载文件与中间数据保存在独立运行目录，操作见 [README](README.md)。

数据署名与许可适用于相应公开数据切片及派生材料，详见 [第三方来源与署名](THIRD_PARTY_NOTICES.md)。
