# 第三方来源与署名

## Building Data Genome Project 2

建筑负荷、天气与元数据来自 [BDG2 作者仓库](https://github.com/buds-lab/building-data-genome-project-2)。

文献：Miller C, Kathirgamanathan A, Picchetti B, et al. *The Building Data Genome Project 2, energy meter data from the ASHRAE Great Energy Predictor III competition*. Scientific Data 7, 368 (2020). DOI: 10.1038/s41597-020-00712-x.

上游许可原文保存在 [experiments/data/raw/LICENSE](experiments/data/raw/LICENSE)，原文标题为 `Attribution-ShareAlike 4.0 Unported`。对应数据切片及派生材料保留来源与署名，具体使用条款见该文件。

本项目的数据加工包括：按训练期质量选择三栋办公楼，将负值标记为缺失、对历史输入前向填补、保留原始评分标签，提取时间与温度特征，生成预测、仿真排程、统计指标和图表。建筑编号沿用上游公开别名。

## 软件依赖

科学计算使用 NumPy、pandas、SciPy / HiGHS、scikit-learn、LightGBM 和 Matplotlib 等工具，版本见 [requirements-lock.txt](requirements-lock.txt)。各依赖通过安装入口获取，许可随各自软件包提供。

原创代码许可状态：仓库尚未声明独立的开源许可。上述数据许可的适用对象为相应数据及派生材料。
