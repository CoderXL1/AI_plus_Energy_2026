# 数据来源与复现

数据来自 Building Data Genome Project 2 作者公开仓库：
https://github.com/buds-lab/building-data-genome-project-2

固定提交版本：`9b97ccbe90096aff42ed4fd6493bf7ae692d7118`。

Miller C, Kathirgamanathan A, Picchetti B, et al. The Building Data Genome Project 2, energy meter data from the ASHRAE Great Energy Predictor III competition. Scientific Data, 2020, 7: 368. DOI: 10.1038/s41597-020-00712-x.

## 原始数据不提交的安排

完整原始电表 CSV 约 174 MB，天气约 19 MB，建筑元数据约 0.27 MB。为避免把与评审无关的大量原始计量放入版本历史，仓库只保留固定下载地址与 SHA256，并由完整重跑入口自动获取。下载后原始文件和中间数据位于被忽略的运行目录。

选样规则只使用训练期质量，并在全部候选办公楼之间按公开编号排序。复现选样仍需下载完整的公开输入，不能只用三栋结果切片来替代该步骤。

## 仓库中保留的数据

`experiments/results/*_forecasts.csv` 含三栋建筑的逐时背景观测切片及预测；其他结果包括候选筛选统计、任务参数、开始时刻、求解状态和指标。它们是公开数据的派生材料或实验输出，不是用户、团队或真实客户的私人数据。

`Bull_office_Anne`、`Eagle_office_Amanda`、`Fox_office_Alice` 是上游数据集公开别名，保留它们用于复核选样与下载对应关系，不是研究成员姓名。没有新增真实地址、个人姓名或联系信息。预约任务由固定种子的程序独立生成，不是实采预约记录。

原始缺失与零读数按固定协议处理。零值事后诊断不改变主结果；120 个缺失背景案例保留排除记录。

原仓库许可原文保存在 [experiments/data/raw/LICENSE](experiments/data/raw/LICENSE)。数据来源和许可说明同时适用于本仓库内对应的公开数据切片及派生材料；原创代码没有因此自动获得同一许可。
