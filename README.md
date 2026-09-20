# TokenShield

面向桌面 Agent 的可观测、可回退上下文优化代理。项目按生产化路线小步演进：先保证透明代理和观测，再逐步增加结构化压缩、缓存、MCP schema 优化和策略回退。

完整路线见 [PLAN.md](PLAN.md)。当前仓库是 M0 工程基线，不宣称已经具备生产能力。

## 快速启动

```bash
cd tokenshield
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
export TOKENSHIELD_UPSTREAM_API_KEY='your-key'
export TOKENSHIELD_UPSTREAM_BASE_URL='https://api.openai.com'
# 价格单位为 USD / 1,000,000 tokens；支持 * 后缀匹配模型族
export TOKENSHIELD_PRICING_JSON='{"gpt-4o*":{"input_per_million":2.5,"output_per_million":10}}'
uvicorn tokenshield.server:app --host 127.0.0.1 --port 8787
```

将桌面 Agent 的 API base URL 指向 `http://127.0.0.1:8787/v1`。指标位于 `GET /metrics/summary`，健康检查位于 `GET /health`。

## 当前边界

- 默认只支持非流式 `/v1/chat/completions`；
- OpenAI 类模型使用 `tiktoken`；不识别的模型安全回退为字符估算；
- 价格通过 `TOKENSHIELD_PRICING_JSON` 注入，不在代码中硬编码；
- 原文保存在本地 SQLite，后续增加 TTL、加密和脱敏；
- 压缩默认可通过 `TOKENSHIELD_COMPRESSION_ENABLED=false` 关闭。

## 生产化路线

1. provider-specific tokenizer/pricing；
2. streaming passthrough；
3. JSON/diff/test-log 专用压缩器；
4. TTL、加密、脱敏和审计；
5. Prometheus/OpenTelemetry；
6. baseline/optimized A/B 评测和自动回退。
