---
order: 13
published: true
title: Monitoring with Prometheus
---

DocuWaves can report how it is doing at `/metrics`, in the text format
Prometheus and every tool that speaks it (Grafana Agent, VictoriaMetrics,
Netdata) read.

## Turning it on

The endpoint is off until you give it a token:

```bash
METRICS_TOKEN=$(openssl rand -hex 32)
```

Set that in your `.env` and restart. From then on, `/metrics` answers a
request that sends the token as a bearer, and nothing else: without it, or
with a wrong one, the answer is the same 404 as on an instance with metrics
off. The numbers say how big your documentation is and how busy the
instance is, which is nobody's business but yours.

## Scraping it

```yaml
scrape_configs:
  - job_name: docuwaves
    scheme: https
    metrics_path: /metrics
    authorization:
      credentials: <your METRICS_TOKEN>
    static_configs:
      - targets: ["docs.example.com"]
```

If Prometheus runs on the same machine, scraping the container directly
(`localhost:8000`) works just as well and skips the reverse proxy.

## What it reports

| Metric | Type | What it is |
|---|---|---|
| `docuwaves_info{version}` | gauge | The running version, always 1 |
| `docuwaves_start_time_seconds` | gauge | When the process started |
| `docuwaves_http_requests_total{method,status}` | counter | Requests answered |
| `docuwaves_http_request_duration_seconds_sum` / `_count` | summary | Time spent answering them |
| `docuwaves_projects` | gauge | Documentation projects |
| `docuwaves_pages{state}` | gauge | Pages, `published` or `draft`; every language and version counts |
| `docuwaves_accounts{role}` | gauge | Accounts per role |
| `docuwaves_scheduled_publications` | gauge | Drafts waiting for their publication time |
| `docuwaves_search_gaps` | gauge | Distinct searches that found nothing |
| `docuwaves_page_feedback_total{helpful}` | counter | Answers to "Was this helpful?" |
| `docuwaves_content_index_last_rebuild_seconds` | gauge | When the content index was last rebuilt |

The request counters start at 0 whenever the container starts, which is
what `rate()` expects. Labels only ever hold a handful of values (never a
path or a page name), so a busy site does not add series.

## Useful queries

- Error rate: `sum(rate(docuwaves_http_requests_total{status=~"5.."}[5m]))`
- Average answer time:
  `rate(docuwaves_http_request_duration_seconds_sum[5m]) / rate(docuwaves_http_request_duration_seconds_count[5m])`
- Is it up: `up{job="docuwaves"}`, from Prometheus itself.

For a quick look without Prometheus, [Diagnostics](/p/docuwaves/pages/diagnostics)
in the admin area shows the state of the instance too.
