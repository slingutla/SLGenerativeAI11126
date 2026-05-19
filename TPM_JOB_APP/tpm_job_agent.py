#!/usr/bin/env python3
"""
TPM Daily Job Agent

Scheduled run (11 PM PST daily via Windows Task Scheduler):
  1. Query LinkedIn's public guest job search for newly posted Technical Program Manager
     roles in the US (filter: posted within last 24h).
  2. Deduplicate against seen_jobs.json so each posting appears only once across runs.
  3. Fetch each job description and score fit (0-100) against the applicant resume
     using Claude (Anthropic API).
  4. Build an HTML digest with an Application Answer Pack (copy-paste fields) and a
     ranked list of jobs with direct Apply links.
  5. Email the digest (with resume PDF attached) and archive a copy to output/.

Not financial/legal advice. Read-only scraping of the public guest endpoint LinkedIn
itself returns to unauthenticated browsers — no login, no automated submit.
"""

from __future__ import annotations

import os
import re
import sys
import json
import html
import time
import hashlib
import smtplib
import logging
import webbrowser
import datetime as dt
from pathlib import Path
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
load_dotenv(REPO_ROOT / ".env.local")

_LOG_DIR = Path(__file__).resolve().parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)
_LOG_FILE = _LOG_DIR / f"{dt.datetime.now().strftime('%Y-%m-%d')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(_LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("tpm_job_agent")


# ----------------------------
# Configuration
# ----------------------------

@dataclass
class AgentConfig:
    profile_path: Path = SCRIPT_DIR / "profile.json"
    seen_jobs_path: Path = SCRIPT_DIR / "seen_jobs.json"
    output_dir: Path = SCRIPT_DIR / "output"
    resume_path: Path = SCRIPT_DIR / "SarathChandraLingutla_Resume2.pdf"

    seen_jobs_retention_days: int = 45
    detail_fetch_delay_sec: float = 1.5
    search_page_delay_sec: float = 2.0
    request_timeout_sec: int = 20

    claude_model: str = "claude-haiku-4-5-20251001"
    claude_max_tokens: int = 400

    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )


CFG = AgentConfig()


# ----------------------------
# Profile + state
# ----------------------------

def load_profile() -> dict[str, Any]:
    with CFG.profile_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_seen_jobs() -> dict[str, str]:
    if not CFG.seen_jobs_path.exists():
        return {}
    try:
        with CFG.seen_jobs_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        log.warning("seen_jobs.json was corrupt — starting fresh.")
        return {}


def save_seen_jobs(seen: dict[str, str]) -> None:
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=CFG.seen_jobs_retention_days)).isoformat()
    pruned = {jid: ts for jid, ts in seen.items() if ts >= cutoff}
    with CFG.seen_jobs_path.open("w", encoding="utf-8") as f:
        json.dump(pruned, f, indent=2)


# ----------------------------
# LinkedIn public job search (guest endpoint)
# ----------------------------

GUEST_SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
JOB_DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
JOB_ID_PATTERN = re.compile(r"/jobs/view/(?:[\w-]*?-)?(\d+)")


def build_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": CFG.user_agent,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    return s


def fetch_search_page(session: requests.Session, profile: dict[str, Any], start: int) -> str:
    sp = profile["search"]
    params = {
        "keywords": sp["role_keywords"],
        "location": sp["location_query"],
        "f_TPR": f"r{sp['posted_within_seconds']}",
        "start": str(start),
        "sortBy": "DD",  # date posted, descending
    }
    url = (
        GUEST_SEARCH_URL + "?" +
        "&".join(f"{k}={quote_plus(v)}" for k, v in params.items())
    )
    log.info("Fetching search page start=%d", start)
    r = session.get(url, timeout=CFG.request_timeout_sec)
    r.raise_for_status()
    return r.text


_CA_LOC_PATTERN = re.compile(r"(?:^|,\s*)(?:ca|california)\b", re.IGNORECASE)


def is_california_location(location: str) -> bool:
    """True if the location string clearly indicates California.

    Matches "San Jose, CA", "California, United States", "California", "CA".
    Rejects "United States" (no state), "Remote", "Cambridge, MA", "Carolina, ..." etc.
    """
    if not location:
        return False
    return bool(_CA_LOC_PATTERN.search(location))


def parse_job_cards(html_chunk: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html_chunk, "html.parser")
    cards = soup.select("li") or soup.select("div.base-card")
    out: list[dict[str, Any]] = []
    for card in cards:
        link = card.select_one("a.base-card__full-link") or card.select_one("a[href*='/jobs/view/']")
        if not link or not link.get("href"):
            continue
        href = link["href"].split("?")[0]
        m = JOB_ID_PATTERN.search(href)
        if not m:
            continue
        job_id = m.group(1)

        title_el = card.select_one("h3.base-search-card__title")
        company_el = card.select_one("h4.base-search-card__subtitle a") or card.select_one("h4.base-search-card__subtitle")
        loc_el = card.select_one("span.job-search-card__location")
        time_el = card.select_one("time")

        out.append({
            "job_id": job_id,
            "url": f"https://www.linkedin.com/jobs/view/{job_id}",
            "title": (title_el.get_text(strip=True) if title_el else "(unknown title)"),
            "company": (company_el.get_text(strip=True) if company_el else "(unknown company)"),
            "location": (loc_el.get_text(strip=True) if loc_el else ""),
            "posted_label": (time_el.get_text(strip=True) if time_el else ""),
            "posted_datetime": (time_el.get("datetime") if time_el else ""),
        })
    return out


def search_new_jobs(session: requests.Session, profile: dict[str, Any]) -> list[dict[str, Any]]:
    sp = profile["search"]
    collected: dict[str, dict[str, Any]] = {}
    start = 0
    page_size = 25
    while len(collected) < sp["max_results_per_run"]:
        try:
            chunk = fetch_search_page(session, profile, start)
        except requests.HTTPError as e:
            log.warning("Search page start=%d failed: %s", start, e)
            break
        cards = parse_job_cards(chunk)
        if not cards:
            log.info("No more job cards at start=%d — stopping pagination.", start)
            break
        ca_cards = [c for c in cards if is_california_location(c["location"])]
        dropped = len(cards) - len(ca_cards)
        new_this_page = 0
        for c in ca_cards:
            if c["job_id"] not in collected:
                collected[c["job_id"]] = c
                new_this_page += 1
        log.info("Page start=%d: %d cards parsed, %d non-CA dropped, %d new.", start, len(cards), dropped, new_this_page)
        if new_this_page == 0:
            break
        start += page_size
        time.sleep(CFG.search_page_delay_sec)
    return list(collected.values())[: sp["max_results_per_run"]]


def fetch_job_description(session: requests.Session, job_id: str) -> str:
    url = JOB_DETAIL_URL.format(job_id=job_id)
    try:
        r = session.get(url, timeout=CFG.request_timeout_sec)
        r.raise_for_status()
    except requests.HTTPError as e:
        log.warning("Detail fetch failed for %s: %s", job_id, e)
        return ""
    soup = BeautifulSoup(r.text, "html.parser")
    desc = soup.select_one("div.description__text") or soup.select_one("div.show-more-less-html__markup")
    if not desc:
        return ""
    text = desc.get_text(separator="\n", strip=True)
    return text[:6000]  # cap to keep prompts cheap


# ----------------------------
# Claude fit-ranking
# ----------------------------

def get_anthropic_client():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        log.warning("ANTHROPIC_API_KEY missing — fit-ranking disabled.")
        return None
    try:
        from anthropic import Anthropic
    except ImportError:
        log.warning("anthropic package not installed — fit-ranking disabled.")
        return None
    return Anthropic(api_key=api_key)


RANK_SYSTEM = """You are a job-fit scoring assistant. The applicant is a Technical Program Manager
with the resume profile provided. For each job description you receive, you must respond with
ONLY a single JSON object on one line — no prose, no code fences — with these keys:
  "score":  integer 0-100  (how well the job fits the applicant)
  "reason": string (<=200 chars, the strongest 1-2 reasons for the score)
  "flags":  array of short strings (e.g. ["requires PhD", "deep ML role", "10+ years AWS"])
Score harshly: TPM = program/project leadership, cross-functional delivery, stakeholder mgmt,
roadmaps. Penalise pure-engineering, data-science, or sales-engineering roles. Reward Oracle/
ERP/MES/PowerBI/Agile context. US-only; remote OK; sponsorship not required but tolerated."""


def rank_job(client, profile: dict[str, Any], job: dict[str, Any], description: str) -> dict[str, Any]:
    if client is None or not description:
        return {"score": 50, "reason": "Unranked (no API key or empty description).", "flags": []}
    user_msg = (
        f"APPLICANT RESUME SUMMARY:\n{profile['resume_summary']}\n\n"
        f"JOB TITLE: {job['title']}\n"
        f"COMPANY: {job['company']}\n"
        f"LOCATION: {job['location']}\n\n"
        f"JOB DESCRIPTION:\n{description}\n\n"
        "Return ONLY the JSON object."
    )
    try:
        resp = client.messages.create(
            model=CFG.claude_model,
            max_tokens=CFG.claude_max_tokens,
            system=RANK_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = resp.content[0].text.strip()
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            raise ValueError(f"No JSON in model output: {raw[:200]}")
        parsed = json.loads(m.group(0))
        return {
            "score": int(parsed.get("score", 50)),
            "reason": str(parsed.get("reason", ""))[:300],
            "flags": [str(x) for x in parsed.get("flags", [])][:5],
        }
    except Exception as e:
        log.warning("Ranking failed for %s: %s", job["job_id"], e)
        return {"score": 50, "reason": "Ranking failed; review manually.", "flags": []}


# ----------------------------
# HTML digest
# ----------------------------

def render_answer_pack(profile: dict[str, Any]) -> str:
    a = profile["applicant"]
    rows = [
        ("First Name", a["first_name"]),
        ("Last Name", a["last_name"]),
        ("Email", a["email"]),
        ("Phone", a["phone"]),
        ("City", a["city"]),
        ("State", f"{a['state']} ({a['state_code']})"),
        ("Country", f"{a['country']} ({a['country_code']})"),
        ("LinkedIn", a["linkedin_url"]),
        ("GitHub", a["github_url"]),
        ("How did you hear about us", a["discovered_source"]),
        ("Willing to relocate", a["willing_to_relocate"]),
        ("Authorized to work in the US", a["work_authorization_us"]),
        ("Will require sponsorship in the future", a["needs_future_sponsorship"]),
        ("Gender", a["gender"]),
        ("Race / Ethnicity", a["race_ethnicity"]),
        ("Veteran status", a["veteran_status"]),
    ]
    rows_html = "".join(
        f"<tr><td style='padding:4px 12px;font-weight:600;color:#555'>{html.escape(k)}</td>"
        f"<td style='padding:4px 12px;font-family:Consolas,monospace'>{html.escape(v)}</td></tr>"
        for k, v in rows
    )
    return (
        "<h2 style='margin-bottom:6px'>Application Answer Pack</h2>"
        "<p style='color:#666;margin-top:0'>Copy-paste these into LinkedIn Easy Apply / employer forms.</p>"
        f"<table style='border-collapse:collapse;background:#fafafa;border:1px solid #ddd'>{rows_html}</table>"
    )


def render_job_card(job: dict[str, Any], idx: int) -> str:
    score = job.get("score", 0)
    color = "#1b7a3f" if score >= 75 else ("#b07b15" if score >= 60 else "#999")
    flags_html = ""
    if job.get("flags"):
        flags_html = "<div style='margin-top:6px;color:#666;font-size:12px'>" + " · ".join(
            f"<span style='background:#eee;padding:2px 6px;border-radius:3px'>{html.escape(f)}</span>"
            for f in job["flags"]
        ) + "</div>"
    return (
        f"<div style='border:1px solid #e0e0e0;border-radius:6px;padding:14px;margin:10px 0'>"
        f"<div style='display:flex;justify-content:space-between;align-items:baseline'>"
        f"<div><strong style='font-size:16px'>#{idx}. {html.escape(job['title'])}</strong>"
        f" — {html.escape(job['company'])}</div>"
        f"<div style='font-size:20px;font-weight:700;color:{color}'>{score}</div>"
        f"</div>"
        f"<div style='color:#666;font-size:13px;margin-top:4px'>"
        f"{html.escape(job['location'])} · {html.escape(job.get('posted_label',''))}</div>"
        f"<div style='margin-top:8px;color:#333'>{html.escape(job.get('reason',''))}</div>"
        f"{flags_html}"
        f"<div style='margin-top:10px'>"
        f"<a href='{html.escape(job['url'])}' "
        f"style='background:#0a66c2;color:#fff;padding:6px 14px;border-radius:4px;text-decoration:none;font-size:14px'>"
        f"Open on LinkedIn &rarr; Easy Apply</a>"
        f"</div>"
        f"</div>"
    )


def build_digest_html(profile: dict[str, Any], ranked: list[dict[str, Any]], run_ts: dt.datetime) -> str:
    threshold = profile["search"]["min_fit_score_to_include"]
    included = [j for j in ranked if j.get("score", 0) >= threshold]
    skipped = len(ranked) - len(included)

    job_cards = "".join(render_job_card(j, i + 1) for i, j in enumerate(included))
    if not included:
        job_cards = "<p style='color:#888'><em>No new postings cleared the fit threshold today.</em></p>"

    return f"""<!doctype html>
<html><body style='font-family:-apple-system,Segoe UI,Arial,sans-serif;max-width:780px;margin:20px auto;color:#222'>
<h1 style='margin-bottom:0'>TPM Daily Job Digest</h1>
<p style='color:#666;margin-top:4px'>Generated {run_ts.strftime('%Y-%m-%d %H:%M %Z')} · {len(included)} new role(s) · {skipped} filtered out</p>
<hr>
{render_answer_pack(profile)}
<hr>
<h2>New roles posted in the last 24h</h2>
{job_cards}
<hr>
<p style='color:#999;font-size:12px'>Generated by TPM_JOB_APP. Source: linkedin.com/jobs (public guest endpoint).
Apply manually — automated submission violates LinkedIn ToS and risks account restriction.</p>
</body></html>"""


# ----------------------------
# Email
# ----------------------------

def send_email(html_body: str, run_ts: dt.datetime, ranked_count: int) -> None:
    host = os.getenv("TPM_SMTP_HOST")
    port = int(os.getenv("TPM_SMTP_PORT", "587"))
    user = os.getenv("TPM_SMTP_USER")
    pw = os.getenv("TPM_SMTP_PASS")
    from_addr = os.getenv("TPM_FROM_EMAIL", user)
    to_addr = os.getenv("TPM_TO_EMAIL")

    if not all([host, user, pw, from_addr, to_addr]):
        log.warning("SMTP env vars not fully set — skipping email (digest still saved to output/).")
        return

    msg = EmailMessage()
    msg["Subject"] = f"TPM Job Digest — {run_ts.strftime('%Y-%m-%d')} ({ranked_count} new)"
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content("Open in an HTML-capable mail client to see the formatted digest.")
    msg.add_alternative(html_body, subtype="html")

    if CFG.resume_path.exists():
        with CFG.resume_path.open("rb") as f:
            msg.add_attachment(
                f.read(),
                maintype="application",
                subtype="pdf",
                filename=CFG.resume_path.name,
            )
    else:
        log.warning("Resume file %s not found — sending digest without attachment.", CFG.resume_path)

    log.info("Sending digest email to %s via %s:%d", to_addr, host, port)
    with smtplib.SMTP(host, port) as smtp:
        smtp.starttls()
        smtp.login(user, pw)
        smtp.send_message(msg)


# ----------------------------
# Main
# ----------------------------

def main() -> int:
    run_ts = dt.datetime.now(dt.timezone.utc).astimezone()
    log.info("=== TPM Job Agent run @ %s ===", run_ts.isoformat())

    profile = load_profile()
    seen = load_seen_jobs()
    session = build_session()

    try:
        all_jobs = search_new_jobs(session, profile)
    except Exception as e:
        log.error("Search failed: %s", e)
        return 2

    log.info("Found %d total postings in last 24h.", len(all_jobs))
    new_jobs = [j for j in all_jobs if j["job_id"] not in seen]
    log.info("%d are new since last run.", len(new_jobs))

    client = get_anthropic_client()
    ranked: list[dict[str, Any]] = []
    for j in new_jobs:
        time.sleep(CFG.detail_fetch_delay_sec)
        desc = fetch_job_description(session, j["job_id"])
        verdict = rank_job(client, profile, j, desc)
        j.update(verdict)
        ranked.append(j)
        seen[j["job_id"]] = run_ts.isoformat()
        log.info("Ranked %s — %s @ %s: %d", j["job_id"], j["title"][:50], j["company"][:30], verdict["score"])

    ranked.sort(key=lambda x: x.get("score", 0), reverse=True)

    CFG.output_dir.mkdir(exist_ok=True)
    digest_html = build_digest_html(profile, ranked, run_ts)
    digest_path = CFG.output_dir / f"digest_{run_ts.strftime('%Y%m%d_%H%M')}.html"
    digest_path.write_text(digest_html, encoding="utf-8")
    log.info("Digest saved: %s", digest_path)

    threshold = profile["search"]["min_fit_score_to_include"]
    included_count = sum(1 for j in ranked if j.get("score", 0) >= threshold)

    if os.getenv("TPM_OPEN_IN_BROWSER", "1") == "1" and included_count > 0:
        try:
            webbrowser.open(digest_path.resolve().as_uri())
            log.info("Opened digest in default browser.")
        except Exception as e:
            log.warning("Could not auto-open browser: %s", e)

    try:
        send_email(digest_html, run_ts, included_count)
    except Exception as e:
        log.error("Email send failed: %s", e)

    save_seen_jobs(seen)
    log.info("=== Run complete: %d new roles, %d above fit threshold ===", len(new_jobs), included_count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
