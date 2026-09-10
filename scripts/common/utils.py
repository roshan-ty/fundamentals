# Bulls & Bears Fundamentals — shared utilities
import json
import os
import sys
import time
import datetime as dt
import subprocess
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_DIR = os.path.join(ROOT, "config")
DATA_DIR = os.path.join(ROOT, "data")


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def config_path(name):
    return os.path.join(CONFIG_DIR, name)


def load_config(name):
    p = config_path(name)
    if not os.path.exists(p):
        raise FileNotFoundError(f"Config not found: {p}")
    with open(p, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_scorecard():
    sc = load_config("scorecard.json")
    # Build id -> dataPoint map per currency for O(1) matching
    for code, cur in sc.get("currencies", {}).items():
        index = {}
        for dp in cur.get("dataPoints", []):
            index[dp["id"]] = dp
        cur["_index"] = index
    return sc


def load_symbols():
    return load_config("symbols.json")


def load_news_rules():
    return load_config("news_rules.json")


def now_iso():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def today_str():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


def log(msg, level="INFO"):
    ts = dt.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{level}] {msg}", flush=True)


def load_json(path, default=None):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            log(f"Corrupt JSON {path}: {exc} — returning default", "WARN")
    return default


def save_json(path, obj, pretty=True):
    ensure_dir(os.path.dirname(path))
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2 if pretty else None, ensure_ascii=False)
    os.replace(tmp, path)
    return path


def merge_into(existing, incoming, id_key="id"):
    """Merge lists of dicts keyed by id (incoming wins)."""
    merged = {item.get(id_key): item for item in (existing or []) if item.get(id_key)}
    for item in incoming:
        if item.get(id_key):
            merged[item[id_key]] = item
    return list(merged.values())


class HttpSession:
    """HTTP helper with retries, backoff and optional quota logging."""

    def __init__(self, timeout=30, max_retries=3, backoff=2.0, user_agent=None):
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff = backoff
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
        )

    def get(self, url, params=None, headers=None, timeout=None, allow_https_only=True):
        last_exc = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(url, params=params, headers=headers, timeout=timeout or self.timeout)
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after and retry_after.isdigit() else self.backoff * attempt
                    log(f"HTTP 429 ({url[:80]}...) — sleeping {wait}s", "WARN")
                    time.sleep(wait)
                    continue
                if resp.status_code >= 500 and attempt < self.max_retries:
                    time.sleep(self.backoff * attempt)
                    continue
                resp.raise_for_status()
                return resp
            except requests.RequestException as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    time.sleep(self.backoff * attempt)
        raise RuntimeError(f"Request failed after {self.max_retries} attempts: {last_exc}")

    def get_json(self, url, params=None, headers=None):
        resp = self.get(url, params=params, headers=headers)
        return resp.json()


def git(*args, cwd=None):
    """Run a git command, return (rc, combined_output)."""
    try:
        proc = subprocess.run(
            ["git", *args], cwd=cwd or ROOT, capture_output=True, text=True, timeout=300
        )
        return proc.returncode, (proc.stdout + proc.stderr).strip()
    except Exception as exc:  # pragma: no cover
        return 1, str(exc)


def commit_and_push(message, cwd=None, files=None):
    """Stage, commit and push. Returns (ok, detail)."""
    if os.environ.get("NO_GIT_PUSH") == "1":
        log("NO_GIT_PUSH set — skipping git operations", "SKIP")
        return True, "skipped"
    rc, out = git("add", "--", *(files if files else ["."]), cwd=cwd)
    if rc != 0:
        return False, out
    diff_rc, diff_out = git("diff", "--cached", "--quiet", cwd=cwd)
    if diff_rc == 0:
        log("No changes to commit", "SKIP")
        return True, "no-changes"
    rc, out = git("commit", "-m", message, cwd=cwd)
    if rc != 0:
        return False, out
    rc, out = git("push", "origin", "HEAD", cwd=cwd)
    if rc != 0 and ("fetch first" in out or "rejected" in out or "non-fast-forward" in out):
        rc2, out2 = git("pull", "--rebase", "origin", cwd=cwd)
        if rc2 == 0:
            rc, out = git("push", "origin", "HEAD", cwd=cwd)
    return rc == 0, out