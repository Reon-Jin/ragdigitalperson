function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderInlineMarkdown(text: string): string {
  let html = escapeHtml(text);
  html = html.replace(/`([^`\n]+)`/g, "<code>$1</code>");
  html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/__([^_]+)__/g, "<strong>$1</strong>");
  html = html.replace(/\*([^*\n]+)\*/g, "<em>$1</em>");
  html = html.replace(/_([^_\n]+)_/g, "<em>$1</em>");
  html = html.replace(/~~([^~]+)~~/g, "<del>$1</del>");
  return html;
}

export function renderMarkdown(text: string): string {
  const source = String(text || "").replace(/\r\n?/g, "\n");
  if (!source.trim()) return "";

  const codeBlocks: string[] = [];
  const withPlaceholders = source.replace(/```([\w-]*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    const index =
      codeBlocks.push(
        `<pre><code${lang ? ` data-lang="${escapeHtml(lang)}"` : ""}>${escapeHtml(code.trimEnd())}</code></pre>`,
      ) - 1;
    return `@@CODEBLOCK_${index}@@`;
  });

  const lines = withPlaceholders.split("\n");
  const html: string[] = [];
  let paragraph: string[] = [];
  let listType: "ul" | "ol" | null = null;
  let quote: string[] = [];

  const flushParagraph = (): void => {
    if (!paragraph.length) return;
    html.push(`<p>${renderInlineMarkdown(paragraph.join("\n")).replace(/\n/g, "<br>")}</p>`);
    paragraph = [];
  };

  const flushList = (): void => {
    if (!listType) return;
    html.push(`</${listType}>`);
    listType = null;
  };

  const flushQuote = (): void => {
    if (!quote.length) return;
    html.push(`<blockquote>${quote.map((item) => `<p>${renderInlineMarkdown(item)}</p>`).join("")}</blockquote>`);
    quote = [];
  };

  lines.forEach((line) => {
    const trimmed = line.trim();
    if (!trimmed) {
      flushParagraph();
      flushList();
      flushQuote();
      return;
    }

    const codeMatch = trimmed.match(/^@@CODEBLOCK_(\d+)@@$/);
    if (codeMatch) {
      flushParagraph();
      flushList();
      flushQuote();
      html.push(codeBlocks[Number(codeMatch[1])]);
      return;
    }

    const headingMatch = trimmed.match(/^(#{1,6})\s+(.*)$/);
    if (headingMatch) {
      flushParagraph();
      flushList();
      flushQuote();
      const level = headingMatch[1].length;
      html.push(`<h${level}>${renderInlineMarkdown(headingMatch[2])}</h${level}>`);
      return;
    }

    const quoteMatch = trimmed.match(/^>\s?(.*)$/);
    if (quoteMatch) {
      flushParagraph();
      flushList();
      quote.push(quoteMatch[1]);
      return;
    }
    flushQuote();

    const unorderedMatch = trimmed.match(/^[-*+]\s+(.*)$/);
    if (unorderedMatch) {
      flushParagraph();
      if (listType !== "ul") {
        flushList();
        listType = "ul";
        html.push("<ul>");
      }
      html.push(`<li>${renderInlineMarkdown(unorderedMatch[1])}</li>`);
      return;
    }

    const orderedMatch = trimmed.match(/^\d+\.\s+(.*)$/);
    if (orderedMatch) {
      flushParagraph();
      if (listType !== "ol") {
        flushList();
        listType = "ol";
        html.push("<ol>");
      }
      html.push(`<li>${renderInlineMarkdown(orderedMatch[1])}</li>`);
      return;
    }

    flushList();
    paragraph.push(trimmed);
  });

  flushParagraph();
  flushList();
  flushQuote();
  return html.join("");
}