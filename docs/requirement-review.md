# 需求质量评估

本模块帮助需求负责人发现需要澄清的问题。模型只接收选中需求的名称、描述、验收条件和版本号，不会读取整个仓库、调用工具、决定业务规则或自动修改需求。原文引用逐字校验；引用有效不代表建议一定正确。

## 面向使用者的操作

1. 打开“需求质量评估”。先看明确标注的synthetic/demo示例，理解“验收条件”就是“怎样判断功能做好了”。
2. 本地工作空间：选择Demo或Live项目，创建并保存需求；在模型连接中选择已配置的云端模型或Ollama。未连接时仍能记录需求和创建任务。
3. 确认文本不含密钥、客户资料等敏感内容，并确认界面显示的接收方，再开始评估。
4. 阅读每条原文、问题和待确认事项，填写理由并采纳或驳回。采纳只表示认可问题，不表示已修复。确认记录不覆盖；修改意见可写入下一次需求修订与新评估。
5. 在需求正文中手动修改并说明原因，保存为新版本，再次评估；旧报告仍可回看，不可用于确认新版需求。
6. 创建关联开发任务，填写计划工时，进入现有协作链路。预计工时不冒充实测耗时。

公网试用只在本页返回结果和记录临时确认，不保存访客文本、评估结果或任务；刷新即丢失。模型供应商仍接收输入并按其政策处理。公网项目数据继续只读，唯一可选例外为无状态 `POST /api/review/trial`。

## Groq 免费套餐配置

本项目以Groq免费套餐作为云端接入示例。配置服务时需注册/登录并确认账号的模型权限和免费额度；本项目不升级套餐或自动充值。参考[兼容接口](https://console.groq.com/docs/openai)、[模型列表](https://console.groq.com/docs/models)、[免费套餐限额](https://console.groq.com/docs/rate-limits)。接入示例：

```dotenv
REVIEW_API_BASE_URL=https://api.groq.com/openai/v1
REVIEW_MODEL=openai/gpt-oss-20b
REVIEW_API_KEY=在本地.env或Render环境变量填写，不提交Git
PUBLIC_REVIEW_ENABLED=false
PUBLIC_REVIEW_DAILY_LIMIT=20
```

模型名称可更换为账号可用且支持Chat Completions JSON模式的模型。配置成功不等于实际可用，真实调用仍可能限流、超时、拒答或输出不合规。不重试计费请求，不回退为模拟答案。最终效果需用真实调用验证。

公网：在现有Render服务Environment填写上述前三项，确认后把PUBLIC_REVIEW_ENABLED设为true，再部署已通过CI的版本。密钥由用户自行输入，不发到聊天。保持READ_ONLY=true。首次可用后用公开模拟文本做验收，禁止把本地数据库上传公网。

额度保护为单进程：一次只处理一个请求、至少间隔15秒、每UTC日最多20次尝试，失败也计数；重启/休眠唤醒后内存保护可能重置，多实例不共享。它不是可靠的金融预算控制，必须保持供应商免费套餐/账户限额，不能据此承诺付费调用永不超额。未做分布式限流或压力测试。

## 本地 Ollama

使用Ollama运行自己选择的模型后设置REVIEW_OLLAMA_ENABLED=true、REVIEW_OLLAMA_MODEL及REVIEW_OLLAMA_BASE_URL（默认http://127.0.0.1:11434/v1）。Docker Desktop后端访问宿主机通常使用http://host.docker.internal:11434/v1；访问权限和监听地址由使用者配置。公网Render的localhost不指向个人电脑。当前未自动安装或下载模型，也未验证具体本机模型速度。

## 接口与数据

- GET /api/requirements：按模式/项目筛选，limit/offset分页。
- PUT /api/requirements/{id}：需expected_version与revision_reason；版本冲突409。更新原接口的调用方也需提供这两个字段。
- GET /api/requirements/{id}/reviews：需求、最近50次评估/修订和关联任务。
- POST /api/requirements/{id}/reviews：provider、expected_version、UUID request_key、consent=true。同一请求标识重复使用不二次调用；超时结果未知时以新标识重试可能额外调用。单需求100秒内限制新评估。
- POST /api/requirement-reviews/{id}/findings/{index}/decision：accepted/rejected与理由；仅当前版本成功报告可确认。
- GET /api/review/connections：连接是否配置，不返回密钥。
- GET/POST /api/review/trial：试用状态/无状态公网评估，默认关闭。

新增RequirementRevision、RequirementReview、ReviewDecision。评估保存需求版本快照、SHA256、Prompt版本、配置模型名、接收地址、耗时、供应商返回的token计数及安全错误代码；不保存未通过校验的原始响应、推理过程或错误正文。缺失用量保持缺失。没有质量总分或模型效果提升承诺。

## 评测与已验证范围

离线测试验证引用、结构、无问题结果的含义、超时/拒答/限流、幂等、版本冲突、只读边界及公网试用不落库。离线Mock结果不能证明模型准确率。

`backend/evals/requirement-cases.json`为6个公开模拟需求，覆盖验收、边界、冲突、充分明确和提示注入；参考分类由开发阶段编写，尚未经独立人工审阅，不称为人工金标准。

```sh
python scripts/evaluate_requirements.py
# 上一条只检查数据集，不调用模型。配置后明确允许6次调用：
python scripts/evaluate_requirements.py --provider cloud --allow-model-call
```

结果写入忽略Git的reports/requirement-eval.json，包含真实失败记录、分类遗漏/额外建议及版本信息，需人工复核。未配置服务时不生成准确率或假报告。真实模型验证结果应在执行后另行记录。
