# FinAvatar 实时金融数据驱动重构方案

## 0. 目标与边界

目标不是把当前项目继续做成“更会聊天的 RAG 页面”，而是重构为一个可本地部署、低延迟、强解释性的金融智能分析数字人工作台。

新产品边界：

- 做数据驱动分析，不做收益承诺
- 做结构化候选和风险提示，不做拍脑袋荐股
- 做受控编排，不做失控 Agent
- 做可追溯引用，不做黑箱式结论

推荐架构原则：

- 模块化单体优先，避免过早微服务
- “实时市场数据引擎 + 金融知识库 RAG 引擎”双引擎
- FastAPI 继续作为后端入口
- 前端升级为独立 `frontend/` 工程，构建后可由 FastAPI 静态托管
- LLM 仅负责路由、解释、总结与格式化，不直接承担事实来源

---

## A. 实时金融数据架构设计

### 1. 总体分层

```text
User / UI
  -> ui_api
  -> orchestration
  -> domain services
  -> dual engines
     -> market_data engine
     -> finance_rag engine
  -> storage / cache / observability
```

### 2. 双引擎结构

#### 实时市场数据引擎

负责：

- 股票 / ETF / 基金 / 指数实时或准实时行情
- 板块强弱、成交榜、涨跌榜
- 技术指标和市场宽度
- 筛选器底层数据

输出统一标准化对象：

- `QuoteSnapshot`
- `FundSnapshot`
- `IndexSnapshot`
- `SectorSnapshot`
- `TechnicalSnapshot`
- `MarketEvent`

#### 金融知识库引擎

负责：

- 财报
- 公告
- 研报
- 政策文件
- 宏观解读
- 行业资料
- 用户上传文档
- 内部研究内容

输出：

- 引文
- 背景逻辑
- 风险证据
- 财报亮点
- 行业驱动

### 3. 数据流

```text
用户提问
-> intent_router
-> task_router
-> hybrid_answer_engine
   -> 实时数据拉取
   -> RAG 检索与重排
   -> 结构化分析模板
   -> response_composer
-> SSE 流式回前端
```

### 4. 缓存策略

| 数据类型 | TTL | 备注 |
|---|---:|---|
| 个股/指数报价 | 5-30 秒 | 高频短缓存 |
| 板块榜单 | 30-120 秒 | 热点榜单短缓存 |
| 基金/ETF 净值快照 | 30-300 秒 | 视源可用性而定 |
| 基本面 | 1 小时-1 天 | 低频变化 |
| 财报/公告/研报 | 长缓存 | 文档入库后长期保存 |
| 问题结果缓存 | 30-180 秒 | 避免重复请求和重复推理 |

### 5. 调度策略

- 打开详情页时触发预取：`quote + profile + news + docs`
- 搜索代码时触发候选预热
- 同一 symbol 的并发请求做 single-flight 去重
- provider 层内置重试、熔断、fallback、并发限制

---

## B. Provider Adapter 设计

### 1. 设计目标

禁止上层代码直接依赖某一家数据源。上层只能依赖接口，不依赖 API 返回格式。

### 2. Provider 类型

```text
QuoteProvider
FundProvider
FundamentalsProvider
NewsProvider
TechnicalIndicatorProvider
ScreenerProvider
SectorProvider
```

### 3. 统一接口

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from pydantic import BaseModel


class ProviderHealth(BaseModel):
    provider: str
    ok: bool
    latency_ms: int | None = None
    error: str | None = None


class QuoteProvider(ABC):
    provider_name: str

    @abstractmethod
    async def get_quote(self, symbol: str, market: str | None = None) -> "QuoteSnapshot":
        raise NotImplementedError

    @abstractmethod
    async def get_quotes(self, symbols: Sequence[str], market: str | None = None) -> list["QuoteSnapshot"]:
        raise NotImplementedError

    @abstractmethod
    async def healthcheck(self) -> ProviderHealth:
        raise NotImplementedError
```

### 4. 适配器落位

```text
market_data/providers/
  base.py
  registry.py
  alpha_vantage.py
  finnhub.py
  akshare.py
  tushare.py
  mock_provider.py
```

### 5. Provider Registry

```python
class ProviderChain:
    def __init__(self, primary, fallbacks):
        self.primary = primary
        self.fallbacks = fallbacks

    async def first_success(self, op_name: str, *args, **kwargs):
        providers = [self.primary, *self.fallbacks]
        last_error = None
        for provider in providers:
            try:
                operation = getattr(provider, op_name)
                return await operation(*args, **kwargs)
            except Exception as exc:
                last_error = exc
                continue
        raise RuntimeError(f"all providers failed: {last_error}")
```

### 6. MVP 推荐链路

- A 股 / ETF / 基金：`AkShareAdapter -> MockMarketDataAdapter`
- 美股 / 国际指数：`FinnhubAdapter -> AlphaVantageAdapter -> MockMarketDataAdapter`
- 本地开发：`MockMarketDataAdapter` 默认启用

### 7. 限流与熔断

每个 provider 独立维护：

- `qps_limit`
- `max_concurrency`
- `timeout_ms`
- `retry_times`
- `circuit_breaker_threshold`

---

## C. 股票 / 基金 / ETF 分析流程

### 1. 股票分析

流程：

1. 识别 symbol / 公司 / 市场
2. 拉取 `QuoteSnapshot`
3. 拉取 `SecurityProfile`
4. 拉取近期新闻和公告
5. 从知识库检索财报、研报、风险章节
6. 生成结构化卡片

输出结构：

- 价格与涨跌
- 成交活跃度
- 基本面摘要
- 近期催化
- 风险因素
- 当前结论
- 证据来源

### 2. 基金 / ETF 分析

流程：

1. 识别基金代码或关键词
2. 拉取 `FundSnapshot`
3. 拉取基金档案、管理人、类别、费率
4. 拉取收益、波动、回撤、风格暴露
5. 结合知识库检索基金说明、持仓风格、主题逻辑
6. 输出收益/波动/回撤/适配人群分析

### 3. 比较分析

流程：

1. 标准化两个或多个标的
2. 对齐时间窗口
3. 计算收益、波动、回撤、换手、估值、新闻催化
4. 输出横向表格与卡片解释

### 4. 板块与热点

流程：

1. 获取板块涨跌和领涨标的
2. 获取相关新闻、政策、研报证据
3. 识别驱动与风险
4. 输出“板块更强的原因”而不是只报涨幅

---

## D. Recommendation Pipeline

### 1. 核心原则

推荐不是“给唯一答案”，而是“给候选、给依据、给风险、给风格适配”。

### 2. 处理步骤

#### Step 1. 问题分类

识别：

- `stock_recommendation_analysis`
- `stock_screening`
- `fund_screening`
- `fund_analysis`
- `stock_compare`

#### Step 2. 风险偏好与边界

如果用户没有明确风险偏好：

- 默认 `neutral`
- 自动附带自然合规说明：
  “以下仅基于当前公开数据、行情快照和已收录资料做分析，不构成个性化投资建议。”

#### Step 3. 候选筛选

股票候选的评分可由这些维度组成：

- 趋势强度
- 成交活跃度
- 波动匹配度
- 基本面稳健度
- 财报质量
- 新闻/公告催化
- 风险惩罚项

基金/ETF 候选维度：

- 近 1 周 / 1 月 / 3 月表现
- 波动率
- 最大回撤
- 风格暴露
- 行业集中度
- 费率

#### Step 4. 知识增强

补充：

- 主营业务 / 产品
- 行业景气
- 近期公告
- 财报亮点
- 关键风险
- 新闻情绪

#### Step 5. 结构化输出

输出 3-5 个候选，每个候选包含：

- 当前价格 / 涨跌 / 成交
- 关注理由
- 驱动因素
- 主要风险
- 适合风格
- 更适合的动作标签

动作标签限定为：

- `观察`
- `逢回调关注`
- `分批跟踪`
- `短期交易观察`
- `中期跟踪`
- `回避`

### 3. 评分骨架

```python
class CandidateScore(BaseModel):
    symbol: str
    momentum: float = 0
    liquidity: float = 0
    fundamentals: float = 0
    catalyst: float = 0
    risk_penalty: float = 0
    suitability: float = 0

    @property
    def total(self) -> float:
        return (
            self.momentum * 0.22
            + self.liquidity * 0.16
            + self.fundamentals * 0.24
            + self.catalyst * 0.18
            + self.suitability * 0.20
            - self.risk_penalty * 0.25
        )
```

---

## E. RAG 与实时数据融合方案

### 1. Query Router

必须升级为如下任务域：

```text
realtime_quote
stock_compare
stock_screening
stock_recommendation_analysis
fund_analysis
fund_screening
earnings_report_analysis
news_explainer
sector_rotation_analysis
finance_knowledge_qa
```

### 2. Hybrid Answer Engine

```python
class HybridAnswerEngine:
    async def run(self, request: UserQuery) -> StructuredAnswer:
        route = await self.intent_router.route(request)

        if route.task_type == "realtime_quote":
            market_bundle = await self.market_service.fetch_quote_bundle(route)
            return self.response_composer.quote_answer(route, market_bundle)

        if route.task_type in {"finance_knowledge_qa", "earnings_report_analysis"}:
            rag_bundle = await self.finance_rag.answer(route)
            return self.response_composer.rag_answer(route, rag_bundle)

        market_bundle = await self.market_service.fetch_analysis_bundle(route)
        rag_bundle = await self.finance_rag.retrieve_context(route)
        return self.response_composer.hybrid_answer(route, market_bundle, rag_bundle)
```

### 3. 融合策略

#### 纯概念问题

- 优先 RAG
- 不强制拉实时数据

#### 实时报价问题

- 优先市场数据 API
- 回答必须携带时间戳

#### 实时 + 分析问题

- 同时拉取实时数据与证据文档
- 回答中拆成“当前数据”“背景逻辑”“风险与不确定性”

### 4. 证据组成展示

前端右侧证据面板必须标出：

- 实时行情
- 新闻
- 财报
- 公告
- 研报
- 知识库文档

---

## F. 金融风格 UI 设计规范

### 1. 设计定位

风格关键词：

- 专业
- 克制
- 稳定
- 高信息密度
- 强结构化
- 工作台感

### 2. 主题系统

#### Dark Theme

- `bg/base`: `#0B1220`
- `bg/panel`: `#111A2E`
- `bg/elevated`: `#16233D`
- `text/primary`: `#E8EEF8`
- `text/secondary`: `#9AA8C7`
- `line/default`: `rgba(148, 163, 184, 0.18)`
- `accent`: `#2F7CF6`
- `accent/soft`: `rgba(47, 124, 246, 0.14)`
- `gold`: `#C7A75B`
- `cyan`: `#2BC4C9`

#### Light Theme

- `bg/base`: `#F4F7FB`
- `bg/panel`: `#FFFFFF`
- `bg/elevated`: `#EEF3FA`
- `text/primary`: `#122033`
- `text/secondary`: `#5B6B82`

### 3. 涨跌色配置

必须支持两套模式：

- `cn_market`: 涨红跌绿
- `intl_market`: 涨绿跌红

### 4. Design System

#### spacing

- `4 / 8 / 12 / 16 / 20 / 24 / 32`

#### typography

- 数字与行情建议使用等宽数字字体
- 标题：`IBM Plex Sans SC` 或 `Noto Sans SC`
- 正文：`PingFang SC`, `Microsoft YaHei`, sans-serif
- 数据：`JetBrains Mono` 或 `IBM Plex Mono`

#### radius

- 卡片：`16`
- 二级面板：`12`
- 输入框：`10`

#### border

- `1px solid var(--line-default)`

#### shadow

- Dark 模式弱阴影，主要依赖边框和层级色
- 不使用大面积柔和发光

#### table style

- 行高紧凑
- 表头固定
- 行 hover 仅弱高亮
- 数字右对齐

#### tag style

- 低饱和背景 + 细边框
- 不使用糖果色

#### chart theme

- K 线和折线图不做花哨动画
- 颜色与主题一致
- 网格线低对比度

---

## G. 页面布局与组件清单

### 1. 总体布局

```text
左侧导航栏 | 中央主工作区 | 右侧证据与辅助区
```

### 2. 页面

#### Dashboard 首页

模块：

- 主要指数卡片
- 市场情绪 / 风险概览
- 热门板块
- 涨跌榜 / 成交榜
- 热门 ETF / 基金
- 数字人欢迎区
- 快捷提问入口
- 最近分析记录

#### 智能问答页

- 对话流
- 结构化分析卡片
- 一键追问区
- 风格切换

#### 个股详情页

- 顶部标题区
- 行情摘要条
- K 线 / 分时图区域
- 关键指标卡
- Tab 区域：概览 / 实时数据 / 新闻 / 财报公告 / AI 分析 / 风险 / 来源

#### 基金 / ETF 详情页

- 基础档案
- 收益曲线
- 回撤图
- 风格暴露
- 对比面板

### 3. 核心组件

```text
layout/
  shell
  sidebar
  topbar
  right_panel

dashboard/
  index_card
  market_sentiment_card
  sector_heatmap
  movers_table
  hot_etf_card

analysis/
  conclusion_card
  risk_card
  metrics_card
  catalyst_card
  earnings_highlight_card
  industry_logic_card
  suitability_card
  evidence_source_card

query/
  ask_box
  quick_action_chips
  mode_switcher

avatar/
  advisor_avatar
  avatar_status
  tone_selector

charts/
  line_chart
  candle_chart
  drawdown_chart
  sector_heatmap_chart
  return_curve_chart
```

### 4. 数字人组件状态

- `idle`
- `thinking`
- `speaking`
- `summarizing`

语气模式：

- `摘要`
- `顾问`
- `教学`

---

## H. 新的前后端目录结构

```text
app/
  api/
    deps.py
    routes/
      chat.py
      dashboard.py
      quote.py
      stock.py
      fund.py
      recommendation.py
      knowledge.py
      profile.py
      admin.py
  core/
    config.py
    constants.py
    logging.py
    settings.py
  market_data/
    providers/
      base.py
      registry.py
      alpha_vantage.py
      finnhub.py
      akshare.py
      tushare.py
      mock_provider.py
    cache/
      ttl_cache.py
      request_deduper.py
    schemas/
      quote.py
      fund.py
      profile.py
      news.py
      sector.py
      screening.py
    service/
      quote_service.py
      fund_service.py
      fundamentals_service.py
      news_service.py
      technical_service.py
      dashboard_service.py
    fallback/
      chain.py
      circuit_breaker.py
    rate_limit/
      limiter.py
      concurrency.py
  screening/
    stock_screener.py
    fund_screener.py
    ranking.py
    filters.py
  recommendation/
    recommendation_engine.py
    suitability.py
    risk_rules.py
    explanation_builder.py
  realtime_analysis/
    quote_analysis.py
    intraday_signal.py
    sector_rotation.py
    market_breadth.py
  finance_rag/
    parser/
    chunker/
    retriever/
    reranker/
    citation/
    doc_router/
  orchestration/
    intent_router.py
    task_router.py
    hybrid_answer_engine.py
    response_composer.py
  prompts/
    realtime_market_answer_prompt.md
    stock_recommendation_analysis_prompt.md
    fund_screening_prompt.md
    market_dashboard_summary_prompt.md
    sector_rotation_prompt.md
  repositories/
    quote_cache_repo.py
    document_repo.py
    profile_repo.py
    watchlist_repo.py
  services/
    llm/
      provider_adapter.py
      deepseek_adapter.py
      qwen_adapter.py
      ollama_adapter.py
  main.py

frontend/
  src/
    app/
    pages/
      dashboard/
      copilot/
      stock/
      fund/
      news/
      settings/
    components/
      layout/
      cards/
      charts/
      tables/
      avatar/
      evidence/
      query/
    features/
      dashboard/
      quote/
      stock-analysis/
      fund-analysis/
      recommendation/
      evidence-panel/
      watchlist/
    styles/
      tokens.css
      theme-dark.css
      theme-light.css
      charts.css
```

---

## I. API 设计

### 1. Dashboard

#### `GET /api/v2/dashboard/overview`

返回：

```json
{
  "indices": [],
  "market_sentiment": {},
  "hot_sectors": [],
  "top_gainers": [],
  "top_turnover": [],
  "hot_etfs": [],
  "latest_reports": []
}
```

### 2. Quote

#### `GET /api/v2/quote/{symbol}`

返回：

```json
{
  "quote": {},
  "technical": {},
  "provider_meta": {
    "provider": "akshare",
    "cached": true,
    "timestamp": "2026-03-17T10:22:03+08:00"
  }
}
```

### 3. Stock Analysis

#### `POST /api/v2/stocks/analyze`

请求：

```json
{
  "symbol": "600519",
  "analysis_mode": "professional",
  "market_style": "cn_market"
}
```

返回：

```json
{
  "summary": {},
  "cards": [],
  "citations": [],
  "news": [],
  "risks": [],
  "followups": []
}
```

### 4. Fund / ETF

#### `POST /api/v2/funds/analyze`
#### `POST /api/v2/funds/compare`
#### `POST /api/v2/funds/screen`

### 5. Recommendation

#### `POST /api/v2/recommendations/stocks`

请求：

```json
{
  "query": "当前应该关注哪些高股息股票",
  "risk_level": "medium",
  "investment_horizon": "medium",
  "analysis_mode": "professional"
}
```

### 6. Hybrid QA

#### `POST /api/v2/copilot/stream`

SSE 事件：

- `ack`
- `route`
- `market_fetch_started`
- `market_fetch_done`
- `rag_fetch_started`
- `rag_fetch_done`
- `analysis_cards`
- `citations`
- `delta`
- `final`

### 7. Prefetch

#### `POST /api/v2/prefetch/security`

用于详情页打开时触发：

```json
{
  "symbol": "600519",
  "tasks": ["quote", "fundamentals", "news", "docs"]
}
```

---

## J. 核心代码骨架

### 1. 标准化 Schema

```python
from pydantic import BaseModel


class QuoteSnapshot(BaseModel):
    symbol: str
    name: str
    market: str
    currency: str
    timestamp: str
    last_price: float | None = None
    change: float | None = None
    change_percent: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    prev_close: float | None = None
    volume: float | None = None
    turnover: float | None = None
    amplitude: float | None = None
    turnover_rate: float | None = None
```

```python
class FundSnapshot(BaseModel):
    fund_code: str
    fund_name: str
    nav: float | None = None
    nav_date: str | None = None
    daily_change: float | None = None
    recent_1w: float | None = None
    recent_1m: float | None = None
    recent_3m: float | None = None
    drawdown: float | None = None
    category: str | None = None
    benchmark: str | None = None
```

```python
class SecurityProfile(BaseModel):
    symbol: str
    company_name: str
    sector: str | None = None
    industry: str | None = None
    exchange: str | None = None
    market_cap: float | None = None
    pe: float | None = None
    pb: float | None = None
    dividend_yield: float | None = None
    roe: float | None = None
    debt_ratio: float | None = None
```

### 2. 市场服务层

```python
class QuoteService:
    def __init__(self, provider_chain, cache, deduper):
        self.provider_chain = provider_chain
        self.cache = cache
        self.deduper = deduper

    async def get_snapshot(self, symbol: str, market: str | None = None) -> QuoteSnapshot:
        cache_key = f"quote:{market or 'auto'}:{symbol}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        async def loader():
            quote = await self.provider_chain.first_success("get_quote", symbol=symbol, market=market)
            await self.cache.set(cache_key, quote, ttl=15)
            return quote

        return await self.deduper.run(cache_key, loader)
```

### 3. Recommendation Engine

```python
class RecommendationEngine:
    def __init__(self, stock_screener, fund_screener, suitability, explainer):
        self.stock_screener = stock_screener
        self.fund_screener = fund_screener
        self.suitability = suitability
        self.explainer = explainer

    async def recommend_stocks(self, context: RecommendationContext) -> RecommendationResult:
        candidates = await self.stock_screener.screen(context)
        ranked = self.suitability.rank(candidates, context)
        top_items = ranked[:5]
        return await self.explainer.build_stock_result(top_items, context)
```

### 4. 响应组合器

```python
class ResponseComposer:
    def hybrid_answer(self, route, market_bundle, rag_bundle) -> dict:
        return {
            "disclaimer": "以下分析基于当前公开数据、市场快照和系统已收录资料，不构成个性化投资建议。",
            "summary_card": self.build_summary_card(route, market_bundle, rag_bundle),
            "risk_card": self.build_risk_card(route, market_bundle, rag_bundle),
            "metric_cards": self.build_metric_cards(market_bundle),
            "evidence_cards": self.build_evidence_cards(rag_bundle),
            "followups": self.build_followups(route),
        }
```

### 5. 流式事件

```python
async def stream_hybrid_answer(request):
    yield {"type": "ack", "message": "正在识别问题类型"}
    route = await router.route(request)
    yield {"type": "route", "task_type": route.task_type}
    yield {"type": "market_fetch_started", "message": "正在拉取实时数据"}
    market_bundle = await market_service.fetch(route)
    yield {"type": "market_fetch_done", "symbols": market_bundle.symbols}
    yield {"type": "rag_fetch_started", "message": "正在匹配知识证据"}
    rag_bundle = await finance_rag.retrieve_context(route)
    yield {"type": "rag_fetch_done", "citations": len(rag_bundle.citations)}
```

---

## K. MVP 实现顺序

### Phase 1. 后端底座

- 新建 `market_data/` 目录
- 定义标准 schema
- 实现 `MockMarketDataAdapter`
- 实现 `AkShareAdapter` 骨架
- 实现缓存、去重、限流、fallback

### Phase 2. 编排升级

- 新建 `task_router.py`
- 新建 `hybrid_answer_engine.py`
- 将当前 `intent_router + retriever + composer` 升级为双引擎编排
- SSE 事件改为“实时数据 -> 证据 -> 分析”

### Phase 3. 分析域能力

- 实现 `stock_screener.py`
- 实现 `fund_screener.py`
- 实现 `recommendation_engine.py`
- 实现 `sector_rotation.py`

### Phase 4. UI 重构

- 引入 `frontend/` 独立工程
- 先完成 Dashboard、问答页、个股详情页、基金详情页
- 再做右侧证据面板与数字人状态组件

### Phase 5. Prompt 与合规

- 新增五类金融 Prompt
- 给推荐分析统一加风险边界
- 禁止绝对化措辞

### Phase 6. 观测与评估

- provider 成功率
- 平均响应时间
- 缓存命中率
- 推荐解释覆盖率
- 风险提示覆盖率

---

## L. 必须删除 / 重写 / 保留的旧模块

### 1. 必须删除或逐步下线

- `static/finavatar.html`
- `static/finavatar.css`
- `static/finavatar.js`

原因：

- 这是单页静态工作台，只适合轻量 demo
- 无法支撑 Dashboard、详情页、图表区、右侧辅助区、组件体系

### 2. 必须重写

- `app/main.py`
  - 改为 `api/routes` 装配式入口
- `app/config.py`
  - 增加 market data provider 配置、缓存配置、限流配置、涨跌色模式配置
- `app/orchestration/*`
  - 从单一 RAG 编排重写为双引擎编排
- `app/schemas.py`
  - 按领域拆分，废弃旧的通用聊天 schema
- `app/api/routes_v1.py`
  - 保留兼容期，新增 `v2` 路由

### 3. 建议保留并升级为适配层

- `app/services/deepseek_client.py`
  - 升级为 `services/llm/provider_adapter.py`
- `app/services/document_store.py`
  - 保留文档持久化思路，升级为 finance_rag 的 repository / parser / chunker 体系
- `app/knowledge_base/*`
  - 可保留已有金融知识库存储基础
- `app/services/training_service.py`
  - 保留训练运行管理，但不作为核心产品路径

### 4. 当前不建议优先投入

- 大规模微调
- 视频级数字人
- Level2 / 逐笔 / 盘口深度功能
- 复杂多 Agent 自主规划

这些都不是 MVP 的关键路径。

---

## Prompt 体系补充

### `realtime_market_answer_prompt`

要求：

- 优先输出行情快照
- 标明时间戳
- 不做扩展臆测

### `stock_recommendation_analysis_prompt`

要求：

- 只能给候选和分析
- 必须附带风险
- 必须说明依据来自实时数据和公开资料
- 严禁收益承诺

### `fund_screening_prompt`

要求：

- 输出候选列表
- 写明筛选逻辑
- 输出适合的风险偏好

### `market_dashboard_summary_prompt`

要求：

- 总结市场情绪
- 点明板块强弱和成交特征
- 给出风险因子

### `sector_rotation_prompt`

要求：

- 输出轮动方向
- 给出驱动因素和持续性判断
- 说明可能的反转风险

---

## 评估要求

### 实时数据可用性

- provider 成功率
- 平均响应时间
- 缓存命中率
- fallback 触发率

### 推荐分析质量

- 数据引用覆盖率
- 风险提示覆盖率
- 夸张表述拦截率
- 结构化输出完整率

### UI 质量

- 导航清晰度
- 信息密度合理性
- 图表与卡片协调性
- 主题一致性

### 交互效率

- 首屏响应时间
- 完整分析时间
- 页面切换耗时

---

## 结论

这次重构的正确方向不是继续优化“聊天”，而是建立一个以数据、证据、模板和风险边界为核心的金融分析平台。

建议执行策略：

1. 保留 FastAPI、知识库、模型接入和训练底座
2. 先做 `market_data + orchestration + screening + recommendation`
3. 再重做前端为金融工作台
4. 最后再补更高级的数据源与可视化

也就是说：保留底层资产，重写中上层产品骨架。
