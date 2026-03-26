import type { ConversationSummary, DocumentDetail, IngestionJob, LibraryFileItem, SearchResultItem } from "../../types";

export const mockDocument: DocumentDetail = {
  doc_id: "demo-cn-broker-outlook",
  filename: "2026Q1_券商策略会纪要.pdf",
  category: "券商策略",
  title: "2026 年一季度券商策略会纪要",
  suffix: ".pdf",
  uploaded_at: "2026-03-25T18:05:00+08:00",
  chunk_count: 36,
  section_count: 7,
  summary:
    "资料核心结论聚焦于流动性边际改善、红利资产估值重估与科技链阶段性修复。策略口径强调“防守资产保留底仓，进攻仓位聚焦景气确认后的盈利兑现能力”。",
  keywords: ["红利重估", "科技修复", "流动性", "盈利验证", "机构配置"],
  status: "completed",
  headings: ["核心判断", "资产配置建议", "行业线索", "风险提示", "月度跟踪框架"],
  sections: [
    {
      section_id: "s1",
      doc_id: "demo-cn-broker-outlook",
      title: "宏观流动性与配置主线",
      order: 1,
      summary: "政策与信用环境边际改善后，权益风险偏好有所修复，但资金仍偏好有现金流和股息支撑的资产。",
      chunk_count: 6,
      previews: [
        {
          chunk_id: "c1",
          chunk_index: 1,
          chunk_title: "流动性对估值的影响",
          chunk_kind: "analysis",
          section_id: "s1",
          section_title: "宏观流动性与配置主线",
          preview: "短端资金利率回落带来的估值支撑更先体现于高股息和低波策略。",
          word_count: 224,
          page_start: 2,
          page_end: 3,
        }
      ]
    },
    {
      section_id: "s2",
      doc_id: "demo-cn-broker-outlook",
      title: "红利资产配置框架",
      order: 2,
      summary: "高股息并非单纯防守，更重要的是现金流稳定性、自由现金流覆盖率和政策敏感度。",
      chunk_count: 8,
      previews: [
        {
          chunk_id: "c9",
          chunk_index: 9,
          chunk_title: "红利资产筛选标准",
          chunk_kind: "framework",
          section_id: "s2",
          section_title: "红利资产配置框架",
          preview: "筛选口径从静态股息率升级到股东回报可持续性与经营现金流兑现。",
          word_count: 180,
          page_start: 6,
          page_end: 7,
        }
      ]
    },
    {
      section_id: "s3",
      doc_id: "demo-cn-broker-outlook",
      title: "科技链修复条件",
      order: 3,
      summary: "科技链并非全面进攻，而是优先观察订单、库存与资本开支三项同步修复。",
      chunk_count: 7,
      previews: [
        {
          chunk_id: "c17",
          chunk_index: 17,
          chunk_title: "AI 算力链的验证节点",
          chunk_kind: "checkpoint",
          section_id: "s3",
          section_title: "科技链修复条件",
          preview: "估值弹性足够高，但真正决定持续性的仍是订单能见度和毛利率拐点。",
          word_count: 202,
          page_start: 11,
          page_end: 12,
        }
      ]
    }
  ],
  chunks: [
    {
      chunk_id: "c1",
      chunk_index: 1,
      chunk_title: "流动性对估值的影响",
      chunk_kind: "analysis",
      section_id: "s1",
      section_title: "宏观流动性与配置主线",
      preview: "短端资金利率回落带来的估值支撑更先体现于高股息和低波策略。",
      word_count: 224,
      page_start: 2,
      page_end: 3,
      text: "报告指出，当前无风险利率下行并不会平均抬升所有资产，而是优先改善高股息、现金流稳定、估值折价较深的板块。机构配置行为的顺序是先修复防守资产，再逐步向景气验证后的成长板块扩散。",
      char_start: 0,
      char_end: 225,
    },
    {
      chunk_id: "c9",
      chunk_index: 9,
      chunk_title: "红利资产筛选标准",
      chunk_kind: "framework",
      section_id: "s2",
      section_title: "红利资产配置框架",
      preview: "筛选口径从静态股息率升级到股东回报可持续性与经营现金流兑现。",
      word_count: 180,
      page_start: 6,
      page_end: 7,
      text: "团队建议将红利资产分为高派现央国企、稳定现金流公用事业和经营改善型周期资产三类，并强调股息覆盖倍数、经营现金流净额和资本开支纪律优先于单一股息率排序。",
      char_start: 226,
      char_end: 406,
    },
    {
      chunk_id: "c17",
      chunk_index: 17,
      chunk_title: "AI 算力链的验证节点",
      chunk_kind: "checkpoint",
      section_id: "s3",
      section_title: "科技链修复条件",
      preview: "估值弹性足够高，但真正决定持续性的仍是订单能见度和毛利率拐点。",
      word_count: 202,
      page_start: 11,
      page_end: 12,
      text: "报告认为科技链可交易的前提是订单拐点、库存去化和资本开支回升出现至少两项共振，其中 AI 算力链比泛半导体更具确定性，但波动也显著更高。",
      char_start: 407,
      char_end: 609,
    }
  ],
  pages: [
    {
      doc_id: "demo-cn-broker-outlook",
      page_number: 1,
      char_start: 0,
      char_end: 220,
      preview: "执行摘要与年度配置框架。",
      text: "执行摘要：2026 年的配置主线不是追逐全面贝塔，而是在红利重估、科技修复与流动性改善之间寻找风险收益比更优的组合。",
      chunks: [],
    },
    {
      doc_id: "demo-cn-broker-outlook",
      page_number: 6,
      char_start: 221,
      char_end: 440,
      preview: "红利资产筛选标准与行业偏好。",
      text: "红利资产应从股东回报持续性出发评估，而非仅比较静态股息率。重点关注能源、运营商、公用事业与现金流改善的工业龙头。",
      chunks: [
        {
          chunk_id: "c9",
          chunk_index: 9,
          chunk_title: "红利资产筛选标准",
          chunk_kind: "framework",
          section_id: "s2",
          section_title: "红利资产配置框架",
          preview: "筛选口径从静态股息率升级到股东回报可持续性与经营现金流兑现。",
          word_count: 180,
          page_start: 6,
          page_end: 7,
        }
      ],
    }
  ],
};

export const mockFiles: LibraryFileItem[] = [
  mockDocument,
  {
    doc_id: "demo-bank-risk",
    filename: "上市银行年报风险复盘.docx",
    category: "银行研究",
    title: "上市银行年报风险复盘",
    suffix: ".docx",
    uploaded_at: "2026-03-24T09:20:00+08:00",
    chunk_count: 28,
    section_count: 6,
    summary: "聚焦净息差、资产质量与资本充足率。",
    keywords: ["净息差", "不良率", "资本补充"],
    status: "completed",
  },
  {
    doc_id: "demo-policy-weekly",
    filename: "政策周报_制造业支持.pdf",
    category: "政策跟踪",
    title: "制造业支持政策周报",
    suffix: ".pdf",
    uploaded_at: "2026-03-26T11:00:00+08:00",
    chunk_count: 0,
    section_count: 0,
    summary: "后台处理中，待提取章节与摘要。",
    keywords: ["政策", "制造业", "财政"],
    status: "processing",
  },
];

export const mockJobs: IngestionJob[] = [
  {
    job_id: "job-demo-1",
    doc_id: "demo-policy-weekly",
    user_id: "demo-user",
    filename: "政策周报_制造业支持.pdf",
    status: "running",
    stage: "摘要生成中",
    progress: 0.68,
    message: "正在提取章节结构",
    retry_count: 0,
    created_at: "2026-03-26T10:58:00+08:00",
    updated_at: "2026-03-26T11:02:00+08:00",
  },
];

export const mockSessions: ConversationSummary[] = [
  {
    conversation_id: "sess-1",
    title: "红利资产配置讨论",
    created_at: "2026-03-24T20:10:00+08:00",
    updated_at: "2026-03-24T20:18:00+08:00",
    message_count: 8,
    last_message_preview: "请基于纪要材料，给出更偏防守的三类候选方向。",
  },
  {
    conversation_id: "sess-2",
    title: "科技链修复节奏",
    created_at: "2026-03-25T14:00:00+08:00",
    updated_at: "2026-03-25T14:26:00+08:00",
    message_count: 12,
    last_message_preview: "如果订单兑现延迟，估值修复是否还成立？",
  },
];

export const mockHits: SearchResultItem[] = [
  {
    doc_id: mockDocument.doc_id,
    filename: mockDocument.filename,
    category: mockDocument.category,
    title: mockDocument.title,
    section_id: "s2",
    section_title: "红利资产配置框架",
    chunk_id: "c9",
    chunk_index: 9,
    chunk_title: "红利资产筛选标准",
    score: 0.93,
    text: "重点关注经营现金流净额与分红覆盖倍数。",
    page_start: 6,
    page_end: 7,
    chunk_kind: "framework",
    metadata: {},
  },
  {
    doc_id: mockDocument.doc_id,
    filename: mockDocument.filename,
    category: mockDocument.category,
    title: mockDocument.title,
    section_id: "s3",
    section_title: "科技链修复条件",
    chunk_id: "c17",
    chunk_index: 17,
    chunk_title: "AI 算力链的验证节点",
    score: 0.87,
    text: "订单拐点、库存去化和资本开支回升至少两项共振。",
    page_start: 11,
    page_end: 12,
    chunk_kind: "checkpoint",
    metadata: {},
  },
];
