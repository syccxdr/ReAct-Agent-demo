## ReAct Agent 执行引擎技术报告

### 背景与目标
- **目标**: 我们的目标是实现一个完整可用的 ReAct 执行引擎，突出执行过程的可观测性与分析能力。
- **现状**: 基于参考资料里的项目代码，补齐了结构化追踪、循环检测、基础工具集与可视化查看器；原生支持 Gemini，在此基础上通过 provider 抽象支持 **Kimi K2**（OpenAI Compatible）。

### 架构总览
- **核心模块**
  - **Agent**: 实现 Reason → Act → Observe 循环与工具编排。
  - **Tools**: `google`（SERP API）、`wikipedia`、`calc`、`file_read`、`file_write`。
  - **Tracer**: 以 JSONL 记录每一步事件与指标，便于分析与可视化。
  - **LLM Provider**: `Gemini`（默认）与 `Kimi K2`（OpenAI 兼容），通过环境变量切换。
  - **Viewer**: 基于 Streamlit 的轨迹可视化与交互筛选。
- **数据流**: user query → prompt 构造 → LLM 产出决策（action/answer）→ 工具调用 → 观察结果写回上下文 → 下一轮思考/终止 → 输出最终答案与全链路事件。

### ReAct 执行循环（最小而完整）
- **思考（Think）**: 组织 `query/history/tools` 成 prompt，请求 LLM。
- **决策（Decide）**: 解析结构化响应（JSON），分支至 `action` 或 `answer`。
- **行动（Act）**: 选择并调用工具，收集 `observation` 回写到历史。
- **收敛**: 达到终止条件（给出 `answer`）或 `max_iterations`；循环检测触发时强制收敛。
- **鲁棒性**: JSON 解析失败/异常时自动重试并记录 error 事件。

### 可观测性设计（Observability）
- **事件类型**: `think / decide / act / observe / error / final / stats`
- **关键字段**:
  - `session_id, step, ts, type, phase, status`
  - `prompt_preview, model_response_preview, tool, reason`
  - `duration_ms, result_preview`
  - `api_calls, token_in, token_out`
  - `error.kind, error.msg`
- **示例（JSONL）**:
```json
{"type":"think","step":1,"prompt_preview":"...","model_response_preview":"...","ts":1710000000000}
{"type":"decide","step":1,"raw":"{\"action\":{\"name\":\"wikipedia\",\"input\":\"Geoffrey Hinton\"}}"}
{"type":"act","step":1,"tool":"wikipedia","duration_ms":132,"result_preview":"{...}"}
{"type":"final","status":"ok","api_calls":3,"token_in":512,"token_out":214,"result_preview":"..."}
```
- **可视化**: 时间线、过滤（`session_id`/类型）、关键字搜索、错误面板、统计（API 次数与 Tokens）。

### 循环检测与恢复
- **触发条件**: 最近 K=4 步“签名”（工具名+输入摘要）多样性≤2。
- **处理策略**:
  - 记录 `error(kind=loop_detected)`；
  - 强制将下一步决策切换为 `NONE` 或直接总结已知信息；
  - 继续一次 `think` 以推动收敛。
- **价值**: 避免无效重复尝试与 token 浪费，提升可控性。

### 工具集
- **搜索**: Google SERP（top N 结果 JSON 化）；Wikipedia（title/summary）。
- **计算**: `calc` 使用安全 AST 支持四则运算与一元运算。
- **文件**: `file_read`/`file_write` 支持预览与写入（限制到项目工作区）。

### 性能画像
- **性能指标**:  
  - 按步耗时（LLM/工具调用），总执行时间  
  - API 调用次数、输入/输出 Tokens（用量画像）  
- **鲁棒性**:  
  - 所有异常均以 `error` 事件记录上下文  
  - 工具失败/缺失、JSON 解析异常、循环检测均有明确恢复路径

### 思维质量评估（可定性/半定量）
- **有效性**: 行动→有用观察的比例（工具命中率）  
- **增量性**: 观察内容的“新信息增量”（去重后新增比）  
- **收敛性**: 单任务平均循环次数、循环检测触发率  
- **成本效率**: Tokens/有效观察的比值、API 调用/最终答案的比值

### 限制与未来工作
- **限制**:  
  - 工具集主要是演示为主，未做权限/沙盒隔离  
  - 仅实现了“单智能体单线程”执行  
  - LLM 输出格式依赖严格 JSON，虽有重试但仍可能受模型漂移影响
- **未来工作**:  
  - Tool Use（函数调用）与参数严格化  
  - 多 Agent 协作与分工（规划/检索/整合）  
  - 记忆库与向量检索，强化跨回合上下文  
  - 更丰富的可视化对比与成本/质量多维评估

### 参考资料
- ReAct Agent 构建（思路参考及代码初版）:  
  - Building ReAct Agents from Scratch: A Hands-On Guide using Gemini  
    `https://medium.com/google-cloud/building-react-agents-from-scratch-a-hands-on-guide-using-gemini-ffe4621d90ae`
- 可视化与交互式查看器（思路参考）：  
  - Building a ReAct Agent from Scratch: A Beginner’s Guide  
    `https://generativeai.pub/building-a-react-agent-from-scratch-a-beginners-guide-4a7890b0667e`
- Kimi K2（OpenAI Chat Completions 兼容）:  
  - Chat Completions `https://platform.moonshot.cn/docs/api/chat`  
  - Tool Use `https://platform.moonshot.cn/docs/api/tool_use`



