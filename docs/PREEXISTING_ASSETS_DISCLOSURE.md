# 赛前资产与赛期新增披露

## 赛前已有资产

- ERP/EEG 隐喻加工的研究选题与真实写作需求；
- 三篇本地论文：Baiocco et al. (2025)、Tang et al. (2025)、Yao et al. (2025)；
- 旧 `ResearchCopilot_ERP_Metaphor` 项目的前期解析经验、数据结构经验和只读安全规则；
- 旧项目生成的 20 篇论文解析草稿与 805 条 `pending` 人工审核队列。

上述 805 条记录不是已审核 Gold 数据，本项目没有把它们宣称为 Gold，也没有直接将其作为 Evidence Pack 证据。

## 赛期内新建并实现

- 独立项目目录与本地仓库；
- Claim Audit / 论断审计规则；
- 论断维度拆解与五类范围风险；
- 三条回到 PDF 指定页码核验的 claim-level evidence record；
- evidence role、directness 与 claim boundary 的锁定规则；
- 人工审核状态和 `needs_fix` 修订门控；
- Markdown、JSON、CSV Evidence Pack；
- PDF SHA256 完整性校验；
- 新的 Streamlit 单页演示界面；
- 自动测试、演示脚本、项目介绍和披露文档。

## 未复制内容

本项目未复制旧项目的主体代码、Streamlit 页面、Qwen 客户端、`.env`、API Key、Zotero/Obsidian 集成或旧生成页面。旧项目仅被只读审计，用于理解前期资产边界并避免把 pending 数据误标为已审核证据。

## 合规边界

源 PDF、旧项目、Zotero、Obsidian 和原始索引均保持只读、未修改。项目不包含 PDF、密钥、隐私数据、模型缓存或已写死的本机绝对路径配置。实际本地路径只存在于被 Git 忽略的 `config.local.json` 中。

