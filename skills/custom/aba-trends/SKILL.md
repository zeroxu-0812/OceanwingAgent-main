---
name: aba-trends
description: Use this skill when the user wants to batch query Amazon ABA keyword rank trends from SIF, including weekly and monthly searchesRank data, CSV outputs, and ECharts line charts that compare multiple keywords across time.
---

# ABA Trends

## Overview

This skill runs the ABA keyword rank trend workflow in the DeerFlow skill layout.
In DeerFlow agent runtime, call the registered capability tool
`run_aba_trends` as the execution step.

The workflow supports one capability:

- Batch query SIF ABA `searchesRank` trends for keywords.
- Fetch weekly trends, monthly trends, or both with `--granularity all`.
- Generate keyword comparison line charts in an ECharts HTML report.
- Write normalized CSV files for each requested granularity.

## Required DeerFlow Fast Path

When `run_aba_trends` is available, call it directly with the user's keywords.
The tool owns validation, SIF execution, registry updates, artifact generation,
download URL construction, and error classification.

Example tool arguments:

```json
{
  "keywords": ["standing desk", "electric standing desk"],
  "granularity": "all",
  "start_date": "2025-01-01",
  "batch_size": 10
}
```

Use the tool response as the response boundary:

- When `result_summary.execution_status` is `completed`, render `chart_embed.markdown` directly in the chat message before any text summary. It is an ECharts iframe preview designed for chat.
- Use `result_summary` for the analysis summary.
- Use `artifact_urls` verbatim for CSV/JSON data downloads. The data table should be provided as download links, not pasted into the chat.
- Treat `aba_trends_report.html` as a secondary full-report download link.
- If `result_summary.execution_status` is `failed`, report `error_type` and `error_message`.
- Do not inspect local output directories or read local artifact paths to answer the user.
- Do not write temporary runner scripts, recreate SIF requests, or call `aba_trend_viewer/server.py` directly inside DeerFlow runtime.

If the tool returns `error_type: sif_auth_failed`, validate configuration with:

```bash
python3 modules/aba-trends/scripts/check_env.py
```

After changing `.env` or `.claude/aba-trends.env`, restart the backend before rerunning the tool.

## Project Root

Use one of these:

- Set environment variable `ABA_TRENDS_ROOT`.
- Pass `--project-root` to the wrapper script.

Local project root used during development:

```bash
/Users/ethan/Ethan-muti-agents/modules/aba-trends
```

In a DeerFlow sandbox, point `--project-root` to the mounted module path, for example:

```bash
/mnt/project/modules/aba-trends
```

## Local Debug Command

Only use the wrapper script outside DeerFlow runtime, for local debugging or
manual verification when the capability tool is unavailable.

```bash
python /mnt/skills/custom/aba-trends/scripts/run_aba_trends.py \
  --project-root "/mnt/project/modules/aba-trends" \
  --keyword "standing desk" \
  --keyword "electric standing desk" \
  --granularity all \
  --start-date 2025-01-01
```

For local macOS execution, use:

```bash
python "skills/custom/aba-trends/scripts/run_aba_trends.py" \
  --project-root "/Users/ethan/Ethan-muti-agents/modules/aba-trends" \
  --keywords "standing desk,electric standing desk" \
  --granularity all \
  --start-date 2025-01-01
```

## Parameters

- `--keyword`: repeatable keyword argument; prefer this when keywords contain commas.
- `--keywords`: comma/newline-separated keyword list.
- `--granularity`: `week`, `month`, or `all`; default is `all`.
- `--start-date` / `--end-date`: optional display filter. Use `YYYY-MM-DD` for weekly data and `YYYY-MM` for monthly-only requests.
- `--batch-size`: SIF accepts at most 10 keywords per request; default is 10.

## DeerFlow Surfaces

- Shared API: `deerflow.community.aba_trends.workflow:run_aba_trends`
- LangChain tool: `deerflow.community.aba_trends.tool:run_aba_trends_tool`
- Gateway router: `app.gateway.routers.aba_trends:router`
- Client mixin: `deerflow.community.aba_trends.client_adapter:AbaTrendsClientMixin`
- Config entry: `run_aba_trends` in the host project's `config.yaml`

## Expected Outputs

The workflow writes final results under:

```bash
<project-root>/output/run_YYYYMMDD_HHMMSS_<run_suffix>/
```

Expected artifacts:

- `aba_trends_chart.html`: ECharts line charts for in-chat keyword comparison.
- `aba_trends_report.html`: full HTML report with charts and summary table.
- `summary.json`: normalized response with dates, rank series, searches series, and per-keyword summaries.
- `week.csv`: weekly ABA rank matrix when weekly data is requested.
- `month.csv`: monthly ABA rank matrix when monthly data is requested.

## Important Notes

- Credentials are loaded by `modules/aba-trends/auth.py` from the module `.env` and token/cookie cache.
- Required SIF credentials are `SIF_PHONE`/`SIF_PASSWORD`, or an equivalent `SIF_AUTH_TOKEN`/cookie environment setup supported by `auth.py`.
- Ranking values are ABA ranks from SIF `searchesRank`; lower values represent better ranks, so the chart y-axis is inverted.
- Use `all` unless the user explicitly asks for only weekly or only monthly trends.
