#!/usr/bin/env python3
"""Fetch latest Linear issues and inject them into linear-analyzer.html, then open it."""

import json
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

CREDENTIALS_FILE = Path.home() / ".claude" / "linear-credentials.json"
HTML_FILE = Path(__file__).parent / "linear-analyzer.html"

LABEL_COLORS = {
    "Feature":      "#BB87FC",
    "Improvement":  "#4EA7FC",
    "Integrations": "#bec2c8",
    "Libraries":    "#eb5757",
    "Review":       "#5e6ad2",
    "Streak":       "#f2c94c",
}
TARGET_LABELS = list(LABEL_COLORS.keys())

QUERY = """
query($since: DateTimeOrDuration!, $labels: [String!]!) {
  issues(
    first: 250
    filter: {
      completedAt: { gt: $since }
      labels: { name: { in: $labels } }
    }
    orderBy: updatedAt
  ) {
    nodes {
      identifier
      title
      url
      completedAt
      state { name }
      team { name }
      labels { nodes { name } }
    }
  }
}
"""

def get_token():
    creds = json.loads(CREDENTIALS_FILE.read_text())
    token = creds.get("linearApiKey")
    if not token:
        print("No linearApiKey found in ~/.claude/linear-credentials.json", file=sys.stderr)
        sys.exit(1)
    return token

def fetch_issues(token):
    since = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
    payload = json.dumps({
        "query": QUERY,
        "variables": {"since": since, "labels": TARGET_LABELS}
    }).encode()

    req = urllib.request.Request(
        "https://api.linear.app/graphql",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": token,
        }
    )

    try:
        resp_obj = urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print("HTTP Error:", e.code, body, file=sys.stderr)
        sys.exit(1)
    with resp_obj as resp:
        data = json.loads(resp.read())

    if "errors" in data:
        print("Linear API errors:", data["errors"], file=sys.stderr)
        sys.exit(1)

    nodes = data["data"]["issues"]["nodes"]
    issues = []
    for n in nodes:
        issues.append({
            "id":          n["identifier"],
            "title":       n["title"],
            "url":         n["url"],
            "completedAt": n["completedAt"],
            "team":        (n.get("team") or {}).get("name", "Unknown"),
            "labels":      [l["name"] for l in n["labels"]["nodes"]],
            "state":       (n.get("state") or {}).get("name", ""),
        })
    return issues

def build_js_array(issues):
    lines = ["["]
    for i in issues:
        lines.append(
            f'  {{ id: {json.dumps(i["id"])}, title: {json.dumps(i["title"])}, '
            f'url: {json.dumps(i["url"])}, completedAt: {json.dumps(i["completedAt"])}, '
            f'team: {json.dumps(i["team"])}, labels: {json.dumps(i["labels"])}, '
            f'state: {json.dumps(i["state"])} }},'
        )
    lines.append("]")
    return "\n".join(lines)

def inject_and_open(issues):
    html = HTML_FILE.read_text()
    fetched = datetime.now().strftime("%b %-d, %Y %-I:%M %p")

    # Replace subtitle
    html = re.sub(
        r'(<p id="subtitle">)[^<]*(</p>)',
        f'\\1Completed issues · last 14 days · all teams · fetched {fetched}\\2',
        html
    )

    # Replace ISSUES array between sentinels
    new_array = f"const ISSUES = {build_js_array(issues)};"
    html = re.sub(
        r"// ISSUES_DATA_START.*?// ISSUES_DATA_END",
        f"// ISSUES_DATA_START\n{new_array}\n// ISSUES_DATA_END",
        html,
        flags=re.DOTALL
    )

    HTML_FILE.write_text(html)
    print(f"Fetched {len(issues)} issues. Opening browser...")
    subprocess.Popen(["xdg-open", str(HTML_FILE)])

if __name__ == "__main__":
    token = get_token()
    issues = fetch_issues(token)
    inject_and_open(issues)
