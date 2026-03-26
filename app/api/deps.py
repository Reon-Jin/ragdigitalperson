from __future__ import annotations

from dataclasses import dataclass

from app.config import get_settings
from app.knowledge_base.finance_store import FinanceKnowledgeBase
from app.knowledge_base.finance_sync import FinanceSyncService
from app.knowledge_base.profile_store import ProfileStore
from app.market_data.cache.request_deduper import RequestDeduper
from app.market_data.cache.ttl_cache import TTLCache
from app.market_data.providers.registry import MarketDataProviderRegistry
from app.market_data.service.dashboard_service import DashboardService
from app.market_data.service.fund_service import FundService
from app.market_data.service.fundamentals_service import FundamentalsService
from app.market_data.service.news_curator import MarketNewsCurator
from app.market_data.service.news_service import NewsService
from app.market_data.service.quote_service import QuoteService
from app.market_data.service.technical_service import TechnicalService
from app.orchestration.citation_builder import CitationBuilder
from app.orchestration.hybrid_answer_engine import HybridAnswerEngine
from app.orchestration.task_router import TaskRouter
from app.recommendation.explanation_builder import ExplanationBuilder
from app.recommendation.recommendation_engine import RecommendationEngine
from app.recommendation.risk_rules import RiskRules
from app.recommendation.suitability import SuitabilityService
from app.retrieval.finance_retriever import FinanceRetriever
from app.screening.fund_screener import FundScreener
from app.screening.stock_screener import StockScreener
from app.services.conversation_store import ConversationStore
from app.services.deepseek_client import CompatibleLLMClient
from app.services.mysql_document_store import DocumentStore
from app.services.agent_memory_store import AgentMemoryStore
from app.services.auth_store import AuthStore
from app.services.stock_resolver import StockResolver
from app.ui_api.dashboard_api import DashboardAPI
from app.ui_api.fund_api import FundAPI
from app.ui_api.quote_api import QuoteAPI
from app.ui_api.recommendation_api import RecommendationAPI
from app.ui_api.stock_api import StockAPI


@dataclass
class AppContainer:
    document_store: DocumentStore
    llm_client: CompatibleLLMClient
    finance_kb: FinanceKnowledgeBase
    finance_sync: FinanceSyncService
    auth_store: AuthStore
    agent_memory_store: AgentMemoryStore
    profile_store: ProfileStore
    finance_retriever: FinanceRetriever
    citation_builder: CitationBuilder
    conversation_store: ConversationStore
    market_registry: MarketDataProviderRegistry
    stock_resolver: StockResolver
    market_cache: TTLCache
    market_request_deduper: RequestDeduper
    quote_service: QuoteService
    fundamentals_service: FundamentalsService
    fund_service: FundService
    news_service: NewsService
    technical_service: TechnicalService
    dashboard_service: DashboardService
    stock_screener: StockScreener
    fund_screener: FundScreener
    recommendation_engine: RecommendationEngine
    dashboard_api: DashboardAPI
    quote_api: QuoteAPI
    stock_api: StockAPI
    fund_api: FundAPI
    recommendation_api: RecommendationAPI
    task_router_v2: TaskRouter
    hybrid_answer_engine: HybridAnswerEngine


def build_container(
    document_store: DocumentStore,
    llm_client: CompatibleLLMClient,
    profile_store: ProfileStore,
    finance_kb: FinanceKnowledgeBase,
    finance_sync: FinanceSyncService,
) -> AppContainer:
    settings = get_settings()
    finance_retriever = FinanceRetriever(document_store, finance_kb)
    citation_builder = CitationBuilder(finance_kb)
    auth_store = AuthStore(settings)
    agent_memory_store = AgentMemoryStore(settings)
    conversation_store = ConversationStore(settings)
    market_registry = MarketDataProviderRegistry(settings)
    stock_resolver = StockResolver(settings, market_registry=market_registry)
    market_cache = TTLCache()
    market_request_deduper = RequestDeduper()
    quote_service = QuoteService(market_registry, market_cache, market_request_deduper, settings)
    fundamentals_service = FundamentalsService(market_registry, market_cache, market_request_deduper, settings)
    fund_service = FundService(market_registry, market_cache, market_request_deduper, settings)
    news_service = NewsService(market_registry, market_cache, market_request_deduper, settings)
    news_curator = MarketNewsCurator()
    technical_service = TechnicalService(market_registry, market_cache, market_request_deduper, settings)
    dashboard_service = DashboardService(market_registry, quote_service, fund_service, news_service, news_curator, market_cache, settings)
    stock_screener = StockScreener(market_registry, quote_service, fundamentals_service, stock_resolver=stock_resolver)
    fund_screener = FundScreener(market_registry, fund_service)
    suitability = SuitabilityService()
    risk_rules = RiskRules()
    explanation_builder = ExplanationBuilder(suitability, risk_rules)
    recommendation_engine = RecommendationEngine(stock_screener, explanation_builder, quote_service, news_service, news_curator)
    dashboard_api = DashboardAPI(dashboard_service)
    quote_api = QuoteAPI(quote_service)
    stock_api = StockAPI(quote_service, fundamentals_service, news_service, news_curator)
    fund_api = FundAPI(fund_service, fund_screener)
    recommendation_api = RecommendationAPI(recommendation_engine)
    task_router_v2 = TaskRouter(stock_resolver=stock_resolver)
    hybrid_answer_engine = HybridAnswerEngine(
        profile_store=profile_store,
        agent_memory_store=agent_memory_store,
        task_router=task_router_v2,
        dashboard_api=dashboard_api,
        news_service=news_service,
        news_curator=news_curator,
        quote_api=quote_api,
        stock_api=stock_api,
        fund_api=fund_api,
        recommendation_api=recommendation_api,
        finance_retriever=finance_retriever,
        citation_builder=citation_builder,
        llm_client=llm_client,
    )
    return AppContainer(
        document_store=document_store,
        llm_client=llm_client,
        finance_kb=finance_kb,
        finance_sync=finance_sync,
        auth_store=auth_store,
        agent_memory_store=agent_memory_store,
        profile_store=profile_store,
        finance_retriever=finance_retriever,
        citation_builder=citation_builder,
        conversation_store=conversation_store,
        market_registry=market_registry,
        stock_resolver=stock_resolver,
        market_cache=market_cache,
        market_request_deduper=market_request_deduper,
        quote_service=quote_service,
        fundamentals_service=fundamentals_service,
        fund_service=fund_service,
        news_service=news_service,
        technical_service=technical_service,
        dashboard_service=dashboard_service,
        stock_screener=stock_screener,
        fund_screener=fund_screener,
        recommendation_engine=recommendation_engine,
        dashboard_api=dashboard_api,
        quote_api=quote_api,
        stock_api=stock_api,
        fund_api=fund_api,
        recommendation_api=recommendation_api,
        task_router_v2=task_router_v2,
        hybrid_answer_engine=hybrid_answer_engine,
    )
