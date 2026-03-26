# FinAvatar Refinement Implementation Plan

> **For Codex:** Execute this plan directly in this session with small, verifiable edits.

**Goal:** Polish the unfinished FinAvatar workspace by fixing markdown rendering, filling missing detail-panel flows, and simplifying stock data providers to `chinafast + mock`.

**Architecture:** Keep the existing FastAPI + static frontend structure. Frontend changes stay in `static/` and work off existing SSE events; backend changes stay in `app/config.py` and `app/market_data/providers/registry.py` so provider selection remains centralized.

**Tech Stack:** FastAPI, vanilla JavaScript, static CSS, Pydantic models

---

## Scope

1. Add safe markdown rendering for streaming assistant output.
2. Complete unfinished detail-panel flows for realtime quote, stock recommendation, fund screening, and finance knowledge QA.
3. Restrict stock data providers to `chinafast` and `mock`.
4. Verify syntax and summarize remaining product gaps.

## Verification

- Frontend: markdown-heavy answers no longer show raw `#`, `-`, `**`, and code fences.
- Frontend: detail panel auto-populates after each completed analysis.
- Backend: market health only reports `chinafast` and `mock`.
- Backend: touched Python modules pass compile checks.
