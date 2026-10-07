# 第三方来源

## Building Data Genome Project 2

作者仓库：https://github.com/buds-lab/building-data-genome-project-2

文献：Miller C, Kathirgamanathan A, Picchetti B, et al. Scientific Data 7, 368 (2020). DOI: 10.1038/s41597-020-00712-x.

本仓库保留了固定版本作者仓库的 [LICENSE 原文](experiments/data/raw/LICENSE)，其原文标题为 `Attribution-ShareAlike 4.0 Unported`。该原文未经本项目改写；请以原始条款为准。

数据加工范围：只按训练期选择三栋办公楼；负值视为缺失、历史输入向前填补、评分标签不填补；提取时间及温度特征；生成预测、仿真任务排程、汇总指标与图表。保留公开建筑别名及来源，不声称数据为团队自采。

## 依赖

科学计算使用 NumPy、pandas、SciPy / HiGHS、scikit-learn、LightGBM、Matplotlib 等，实际依赖版本见 `requirements-lock.txt`。仓库不重新打包这些依赖的实现或本机二进制运行库。
