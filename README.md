# NeuroTrace

> ERP/EEG 科研论断防火墙

NeuroTrace 是一个窄范围、离线、可复现的黑客松 MVP。它不替研究者“多读几篇论文”，而是在科研论断进入论文前，把论断拆成可核验条件，并阻止真实证据被写成范围过大的结论。

## 问题与真实用户

第一真实用户是正在开展 ERP/EEG 隐喻加工研究、需要撰写综述和论文的研究者本人。普通长文本问答能够流畅总结论文，但长上下文并不会自动保证引用边界正确：模型仍可能把限定于特定研究对象、语境、隐喻类型、任务和加工阶段的发现，压缩成跨条件的统一结论。

本项目只审计一条黄金论断：

> Supportive contexts consistently facilitate metaphor comprehension by reducing N400 amplitudes across metaphor types.

预期且确定性的结论为 `Overgeneralized / 过度概括`。

## 唯一演示路径

1. 打开首页，保留预置论断。
2. 点击“编译证据边界”。
3. 查看 7 个论断维度和 5 个范围风险。
4. 展开 Tang、Yao、Baiocco 三张证据卡，核对研究范围、ERP 时间窗、页码、图号和引用边界。
5. 为每条证据选择 `approve`、`needs_fix` 或 `reject`；`needs_fix` 必须填写修订值。
6. 查看安全改写与范围变化。
7. 下载 Markdown、JSON 或 CSV Evidence Pack。

其中 Tang 是 `conditional_support`，Yao 是 `direct_qualifier_or_counterevidence`，Baiocco 永久锁定为 `boundary_evidence`。即使人工批准 Baiocco，它也不会被升级成“支持性语境降低 N400”的直接证据。

## 可选扩展：20 篇论文审核台

需要继续个人语料清洗时，可直接访问 `/证据审核`。页面从 Zotero collection 读取真实论文名、作者、年份和 PDF 附件，不再把内部 `paper_id` 当作论文标题；原始队列与 Zotero 均保持只读。

805 条记录全部是机器生成的待审核候选，不是 Gold。页面默认使用 59 条核心证据集：20 条论文主卡、20 条实验单元，以及 19 篇含图表论文中各 1 条最有结果证据价值的图表。只有人工审核为“通过”的记录才计入 Gold；需要全面清洗章节结构时，可在侧栏切换到全部 805 条。

审核页会重新打开 Zotero PDF，检查候选页码、尝试定位标题或图表 caption，并从当前 PDF 渲染页面或图表截图。自动定位只是导航辅助，`approve` 前必须由审核人勾选“已在原始 PDF 页面中人工确认”。审核结果独立保存在 `outputs/corpus_reviews.json`，可导出 JSON 或 CSV。

Collection 中 2 个独立 PDF 没有父文献元数据，其题名、作者和年份按 PDF 首页校准，记录在 `data/zotero_metadata_overrides.json`；网站会把来源显示为“PDF 首页校准”，不会冒充 Zotero 父条目元数据。

`127.0.0.1:23119` 是 Zotero 本地 API，不是可浏览的网站；直接打开出现 `No endpoint found` 不表示连接失败。使用审核页前请保持 Zotero Desktop 运行，并在 `config.local.json` 配置：

```json
{
  "zotero_collection_key": "TIGIF3TV",
  "review_queue_path": "本机 human_review_queue.json 路径",
  "literature_index_path": "本机 literature_index.csv 路径",
  "generated_notes_dir": "本机 04_generated_notes 路径"
}
```

页面截图依赖 Poppler 的 `pdftoppm`。Codex Desktop bundled runtime 已提供该命令；在其他机器运行时需安装 Poppler 并确保 `pdftoppm` 在 `PATH` 中。

## 核心能力

- 离线、确定性的黄金论断维度拆解与风险审计；
- 三条回到源 PDF 指定页码核验的 claim-level evidence record；
- 证据角色与 directness 锁定；
- 人工审核门控：`pending` / `approve` / `needs_fix` / `reject`；
- Markdown、JSON、CSV 三种可回读 Evidence Pack；
- PDF SHA256 起止完整性核验；
- 一键恢复演示，状态不依赖上一次 session。

## 安装与运行

要求 Python 3.9+。

```powershell
cd "<neurotrace-claim-firewall 项目目录>"
python -m pip install -r requirements.txt
Copy-Item config.local.example.json config.local.json
```

在 `config.local.json` 中填写三篇只读 PDF 所在目录；该文件已被 Git 忽略。也可以设置环境变量 `NEUROTRACE_PDF_DIR`。

```powershell
streamlit run app.py
```

默认入口通常是 [http://localhost:8501](http://localhost:8501)。黄金路径不需要 API Key，也不需要网络。

默认导航已锁定为比赛首页。20 篇论文审核台仍可通过 `http://localhost:8501/证据审核` 直达，但它不是评委演示内容。

## 测试

```powershell
python -m pytest -q
```

测试覆盖：黄金结论与五类风险、三篇证据角色、审核门控、修订值替换、三种导出回读、哈希计算，以及本机存在源 PDF 时的真实完整性校验。

## 工程结构

```text
app.py                       Streamlit 唯一页面
src/claim_audit.py           确定性论断拆解与审计
src/evidence_store.py        三条锁定证据记录
src/review_store.py          人工审核门控
src/exporter.py              Markdown / JSON / CSV 导出
src/source_integrity.py      只读 SHA256 校验
data/gold_evidence.json      三条 PDF 核验证据
tests/                       核心验收测试
docs/                        比赛介绍、演示与披露文档
```

## 当前范围

黄金论断演示仍只覆盖 3 篇论文和 1 条论断。新增审核台可读取 Zotero collection 中的 20 篇 seed paper 与 805 条候选队列，但这些记录在人工处理前仍是 `pending`，不能称为 Gold。项目不是通用 RAG，不提供任意科研问题问答，不自动写整篇论文，也不写入 Zotero 或 Obsidian。

## 赛前与赛期资产披露

赛前资产包括研究选题、3 篇本地论文，以及旧 Research Copilot 的前期解析经验。赛期内新建并独立实现的核心包括 Claim Audit、证据角色与引用边界判断、人工审核门控、Evidence Pack 导出、源文件完整性校验、测试和新的单页演示界面。旧项目代码、页面、密钥和 `.env` 均未复制。详见 [docs/PREEXISTING_ASSETS_DISCLOSURE.md](docs/PREEXISTING_ASSETS_DISCLOSURE.md)。

## 比赛交付资料

- [项目介绍](docs/PROJECT_INTRO.md)
- [3 分钟 / 5 分钟演示脚本](docs/DEMO_SCRIPT.md)
- [提交页可粘贴文案](docs/SUBMISSION_COPY.md)
- [录屏交接清单](docs/VIDEO_RECORDING_CHECKLIST.md)
- [最终上传检查清单](docs/FINAL_SUBMISSION_CHECKLIST.md)
- [赛前资产与赛期新增披露](docs/PREEXISTING_ASSETS_DISCLOSURE.md)
- [第三方与 AI 工具使用披露](docs/THIRD_PARTY_AND_AI_DISCLOSURE.md)

## 隐私、版权与安全

- 源 PDF 只读，不提交到仓库，也不随 Evidence Pack 导出全文；
- Evidence Pack 只导出 PDF 文件名和哈希，不导出本机绝对路径；
- 证据记录只保留忠实释义、条件、时间窗、页码和图号，不大段复制论文；
- `.env`、`config.local.json`、PDF、密钥和模型缓存均由 `.gitignore` 排除；
- 不调用在线模型，不上传论文内容；
- 本项目不会修改、移动、重命名或覆盖源 PDF、Zotero、Obsidian 或旧项目。

第三方与 AI 使用说明见 [docs/THIRD_PARTY_AND_AI_DISCLOSURE.md](docs/THIRD_PARTY_AND_AI_DISCLOSURE.md)。
