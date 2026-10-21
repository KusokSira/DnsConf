"""Keep the two locally verified ChatGPT rewrites after the donor import."""

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

PINS = {"chatgpt.com": "193.233.112.68", "auth.openai.com": "193.233.112.68"}


class NextDNS:
    def __init__(self, profile, key):
        if not re.fullmatch(r"[0-9a-f]{6}", profile) or not key or "," in key:
            raise ValueError("A single NextDNS CLIENT_ID and AUTH_SECRET are required")
        self.url = f"https://api.nextdns.io/profiles/{profile}/rewrites"
        self.key = key

    def request(self, method, suffix="", payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(
            self.url + suffix, data=data, method=method,
            headers={"X-Api-Key": self.key, "Content-Type": "application/json"},
        )
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    raw = response.read()
                result = json.loads(raw) if raw else {}
                if result.get("errors"):
                    raise RuntimeError(f"NextDNS rejected {method}")
                return result.get("data")
            except urllib.error.HTTPError as error:
                if error.code == 429 and attempt < 2:
                    error.close()
                    time.sleep(60)
                    continue
                status = error.code
                error.close()
                raise RuntimeError(f"NextDNS {method} failed: HTTP {status}") from None
            except (urllib.error.URLError, TimeoutError):
                raise RuntimeError(f"NextDNS {method} network error") from None
        raise RuntimeError("NextDNS rate limit did not clear")

    def rows(self):
        rows = self.request("GET")
        if not isinstance(rows, list):
            raise RuntimeError("Invalid NextDNS rewrite response")
        if any(not isinstance(row, dict) or not all(k in row for k in ("id", "name", "content")) for row in rows):
            raise RuntimeError("Incomplete NextDNS rewrite response")
        return rows

    def remove(self, row):
        self.request("DELETE", "/" + urllib.parse.quote(str(row["id"]), safe=""))

    def add(self, name, content):
        self.request("POST", payload={"name": name, "content": content})


def apply_pins(api, pins=PINS):
    rows = api.rows()
    for name, content in pins.items():
        old = [row for row in rows if row["name"] == name]
        kept = next((row for row in old if row["content"] == content), None)
        removed = []
        try:
            for row in old:
                if row is not kept:
                    api.remove(row)
                    removed.append(row)
            if kept is None:
                api.add(name, content)
        except Exception:
            current = api.rows()
            if not any(row["name"] == name and row["content"] == content for row in current):
                for row in removed:
                    if not any(r["name"] == name and r["content"] == row["content"] for r in current):
                        api.add(name, row["content"])
                        current.append(row)
                raise
    actual = api.rows()
    for name, content in pins.items():
        if [row["content"] for row in actual if row["name"] == name] != [content]:
            raise RuntimeError(f"Read-back failed for {name}")
        print(f"Verified rewrite: {name} -> {content}")


if __name__ == "__main__":
    if os.environ.get("DNS", "").upper() != "NEXTDNS":
        raise SystemExit("This repair step supports a single NEXTDNS profile only")
    apply_pins(NextDNS(os.environ.get("CLIENT_ID", ""), os.environ.get("AUTH_SECRET", "")))
