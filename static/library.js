const catalogList = document.getElementById("catalog-list");
const detailView = document.getElementById("detail-view");
const filenameFilter = document.getElementById("filename-filter");
const categoryFilter = document.getElementById("category-filter");
const titleFilter = document.getElementById("title-filter");
const chunkFilter = document.getElementById("chunk-filter");

let catalog = [];
let selectedDocId = null;

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function queryParams() {
  return new URLSearchParams(window.location.search);
}

function chunkMatches(item, query) {
  if (!query) {
    return true;
  }
  return item.chunks.some((chunk) => chunk.chunk_title.toLowerCase().includes(query));
}

function matchesFilter(item) {
  const filenameQuery = filenameFilter.value.trim().toLowerCase();
  const categoryQuery = categoryFilter.value;
  const titleQuery = titleFilter.value.trim().toLowerCase();
  const chunkQuery = chunkFilter.value.trim().toLowerCase();

  if (filenameQuery && !item.filename.toLowerCase().includes(filenameQuery)) {
    return false;
  }
  if (categoryQuery && item.category !== categoryQuery) {
    return false;
  }
  if (titleQuery && !item.title.toLowerCase().includes(titleQuery)) {
    return false;
  }
  if (!chunkMatches(item, chunkQuery)) {
    return false;
  }
  return true;
}

function renderCategoryOptions() {
  const categories = Array.from(new Set(catalog.map((item) => item.category)));
  categoryFilter.innerHTML = `<option value="">全部类型</option>${categories
    .map((item) => `<option value="${escapeHtml(item)}">${escapeHtml(item)}</option>`)
    .join("")}`;
}

function updateUrl(params) {
  const url = new URL(window.location.href);
  Object.entries(params).forEach(([key, value]) => {
    if (value) {
      url.searchParams.set(key, value);
    } else {
      url.searchParams.delete(key);
    }
  });
  window.history.replaceState({}, "", url);
}

function renderCatalog() {
  const items = catalog.filter(matchesFilter);
  if (!items.length) {
    catalogList.innerHTML = `
      <div class="empty-state">
        <strong>没有匹配的资料</strong>
        <p class="muted small">调整筛选条件后再试。</p>
      </div>
    `;
    return;
  }

  catalogList.innerHTML = items
    .map(
      (item) => `
        <article class="catalog-item ${item.doc_id === selectedDocId ? "is-active" : ""}" data-doc-id="${item.doc_id}">
          <button class="catalog-open-button" data-open-doc="${item.doc_id}" type="button">
            <div class="file-tag-row">
              <span class="tag">${escapeHtml(item.category)}</span>
              <span class="muted small">${item.chunks.length} 个分段</span>
            </div>
            <div class="file-name">${escapeHtml(item.title)}</div>
            <div class="muted small">${escapeHtml(item.filename)}</div>
            <div class="file-summary">${escapeHtml(item.summary)}</div>
            <div class="chunk-tag-wall">
              ${item.keywords.map((keyword) => `<span class="mini-tag">${escapeHtml(keyword)}</span>`).join("")}
            </div>
          </button>
          <div class="catalog-item-actions">
            <button class="secondary-button compact-button" data-open-doc="${item.doc_id}" type="button">查看</button>
            <button class="danger-button compact-button" data-delete-doc="${item.doc_id}" type="button">删除</button>
          </div>
        </article>
      `
    )
    .join("");

  catalogList.querySelectorAll("[data-open-doc]").forEach((button) => {
    button.addEventListener("click", () => openDocument(button.dataset.openDoc));
  });
  catalogList.querySelectorAll("[data-delete-doc]").forEach((button) => {
    button.addEventListener("click", () => deleteDocument(button.dataset.deleteDoc));
  });
}

function setDetailLoading(text) {
  detailView.innerHTML = `
    <div class="empty-state">
      <strong>${escapeHtml(text)}</strong>
      <p class="muted small">请稍候。</p>
    </div>
  `;
}

function findCatalogItem(docId) {
  return catalog.find((item) => item.doc_id === docId) || null;
}

function renderDocument(doc) {
  detailView.innerHTML = `
    <div class="detail-header">
      <div class="file-tag-row">
        <span class="tag">${escapeHtml(doc.category)}</span>
        <span class="muted small">${doc.chunk_count} 个分段</span>
      </div>

      <div class="editor-row">
        <input id="doc-title-input" class="title-editor" type="text" value="${escapeHtml(doc.title)}" maxlength="120" />
        <button id="save-doc-title" class="secondary-button" type="button">保存大标题</button>
        <button id="delete-doc-button" class="danger-button" type="button">删除文献</button>
      </div>

      <div class="detail-meta-grid">
        <div class="detail-block">
          <div class="detail-label">原始文件名</div>
          <div class="detail-value">${escapeHtml(doc.filename)}</div>
        </div>
        <div class="detail-block">
          <div class="detail-label">大意概括</div>
          <div class="detail-value">${escapeHtml(doc.summary)}</div>
        </div>
        <div class="detail-block">
          <div class="detail-label">关键词</div>
          <div class="keyword-wall">
            ${doc.keywords.length ? doc.keywords.map((keyword) => `<span class="mini-tag">${escapeHtml(keyword)}</span>`).join("") : '<span class="muted small">暂无关键词</span>'}
          </div>
        </div>
      </div>
    </div>

    <div class="chunk-library-list">
      ${doc.chunks
        .map(
          (chunk) => `
            <article class="chunk-card library-chunk-card" id="chunk-${chunk.chunk_id}">
              <div class="chunk-header-row">
                <div class="chunk-source">${escapeHtml(chunk.section_title)} · 分段 ${chunk.chunk_index + 1}</div>
                <div class="muted small">${chunk.word_count} 词</div>
              </div>
              <div class="editor-row">
                <input class="chunk-title-editor" data-chunk-input="${chunk.chunk_id}" type="text" value="${escapeHtml(chunk.chunk_title)}" maxlength="80" />
                <button class="secondary-button" data-save-chunk="${chunk.chunk_id}" type="button">保存小标题</button>
              </div>
              <div class="chunk-text">${escapeHtml(chunk.text)}</div>
            </article>
          `
        )
        .join("")}
    </div>
  `;

  const saveDocTitleButton = document.getElementById("save-doc-title");
  const deleteDocButton = document.getElementById("delete-doc-button");

  saveDocTitleButton.addEventListener("click", () => saveDocumentTitle(doc.doc_id));
  deleteDocButton.addEventListener("click", () => deleteDocument(doc.doc_id));

  detailView.querySelectorAll("[data-save-chunk]").forEach((button) => {
    button.addEventListener("click", () => saveChunkTitle(doc.doc_id, button.dataset.saveChunk));
  });

  const targetChunkId = queryParams().get("chunk");
  if (targetChunkId) {
    const targetNode = document.getElementById(`chunk-${targetChunkId}`);
    if (targetNode) {
      targetNode.scrollIntoView({ behavior: "smooth", block: "start" });
      targetNode.classList.add("chunk-highlight");
      window.setTimeout(() => targetNode.classList.remove("chunk-highlight"), 1800);
    }
  }
}

async function openDocument(docId, chunkId = null) {
  selectedDocId = docId;
  updateUrl({ doc: docId, chunk: chunkId });
  renderCatalog();
  setDetailLoading("正在加载文献详情");

  const response = await fetch(`/api/library/${docId}`);
  if (!response.ok) {
    detailView.innerHTML = `
      <div class="empty-state">
        <strong>加载失败</strong>
        <p class="muted small">这篇文献可能已经被删除。</p>
      </div>
    `;
    return;
  }

  const doc = await response.json();
  renderDocument(doc);
}

async function saveDocumentTitle(docId) {
  const input = document.getElementById("doc-title-input");
  const title = input.value.trim();
  if (!title) {
    return;
  }

  const response = await fetch(`/api/library/${docId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!response.ok) {
    return;
  }

  const doc = await response.json();
  const item = findCatalogItem(docId);
  if (item) {
    item.title = doc.title;
  }
  renderCatalog();
  renderDocument(doc);
}

async function saveChunkTitle(docId, chunkId) {
  const input = detailView.querySelector(`[data-chunk-input="${chunkId}"]`);
  if (!input) {
    return;
  }

  const chunkTitle = input.value.trim();
  if (!chunkTitle) {
    return;
  }

  const response = await fetch(`/api/library/${docId}/chunks/${chunkId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chunk_title: chunkTitle }),
  });
  if (!response.ok) {
    return;
  }

  const updatedChunk = await response.json();
  const item = findCatalogItem(docId);
  if (item) {
    const chunk = item.chunks.find((entry) => entry.chunk_id === chunkId);
    if (chunk) {
      chunk.chunk_title = updatedChunk.chunk_title;
    }
  }
  renderCatalog();
  await openDocument(docId, chunkId);
}

async function deleteDocument(docId) {
  const item = findCatalogItem(docId);
  const label = item ? item.title : "这篇文献";
  const confirmed = window.confirm(`确定要删除“${label}”吗？删除后将从知识库和浏览器中移除。`);
  if (!confirmed) {
    return;
  }

  const response = await fetch(`/api/library/${docId}`, { method: "DELETE" });
  if (!response.ok) {
    return;
  }

  catalog = catalog.filter((entry) => entry.doc_id !== docId);
  renderCategoryOptions();

  if (selectedDocId === docId) {
    selectedDocId = catalog[0]?.doc_id || null;
    updateUrl({ doc: selectedDocId, chunk: null });
    renderCatalog();
    if (selectedDocId) {
      await openDocument(selectedDocId);
    } else {
      detailView.innerHTML = `
        <div class="empty-state">
          <strong>文献库为空</strong>
          <p class="muted small">返回主页上传新的资料后，这里会显示文献详情。</p>
        </div>
      `;
    }
    return;
  }

  renderCatalog();
}

async function loadCatalog() {
  const response = await fetch("/api/library/catalog");
  catalog = await response.json();
  renderCategoryOptions();

  const params = queryParams();
  selectedDocId = params.get("doc") || catalog[0]?.doc_id || null;
  renderCatalog();

  if (selectedDocId) {
    await openDocument(selectedDocId, params.get("chunk"));
  }
}

[filenameFilter, categoryFilter, titleFilter, chunkFilter].forEach((element) => {
  element.addEventListener("input", renderCatalog);
  element.addEventListener("change", renderCatalog);
});

loadCatalog();
