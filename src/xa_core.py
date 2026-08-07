#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xa_core - κοινός πυρήνας για όλες τις εκδόσεις (desktop, Android, web).

Περιέχει τη λήψη και ανάγνωση των δεδομένων από το capital.gr και τη
διαχείριση του χαρτοφυλακίου. Δεν έχει τίποτα σχετικό με γραφικά, ούτε
εξωτερικές βιβλιοθήκες - μόνο Python standard library.
"""

import gzip
import json
import os
import re
import ssl
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime
from html import unescape
from html.parser import HTMLParser

__all__ = [
    "MARKETS", "fetch_html", "fetch_index", "fetch_market",
    "fetch_realtime", "parse_realtime", "realtime_share",
    "parse_quotes", "parse_quote_page", "parse_index", "parse_number",
    "fmt", "fmt_int", "fmt_compact", "Portfolio", "portfolio_rows",
]

# ---------------------------------------------------------------------------
# Ρυθμίσεις
# ---------------------------------------------------------------------------

MARKETS = {
    "el": {
        "label": "Χρηματιστήριο Αθηνών (ΧΑ)",
        "short": "ΧΑ",
        "url": "https://www.capital.gr/finance/el/allstocks/1/",
        "indices": [
            ("ΓΔ", "ΓΔ"),
            ("ftse", "FTSE"),
        ],
    },
    "cy": {
        "label": "Χρηματιστήριο Κύπρου (ΧΑΚ)",
        "short": "ΧΑΚ",
        "url": "https://www.capital.gr/finance/cy/allstocks/1/",
        "indices": [
            ("ΓΕΝ_Δ_Κ", "ΓΔ ΧΑΚ"),
            ("ftse20_c", "FTSE/CySE 20"),
        ],
    },
}

QUOTE_URL = "https://www.capital.gr/finance/quote/{}/"

# --- Πηγή πραγματικού χρόνου ------------------------------------------------
# Το capital.gr δίνει τιμές με 15' καθυστέρηση (το δηλώνει σε κάθε σελίδα του).
# Η Ναυτεμπορική δημοσιεύει τιμές πραγματικού χρόνου, σε σελίδα που διαβάζεται
# κανονικά (χωρίς JavaScript). Χρησιμοποιούμε:
#   - Ναυτεμπορική -> τιμή, διαφορά, μεταβολή %, ώρα πράξης, προηγ. κλείσιμο
#   - capital.gr   -> όγκος, αγορά/πώληση (δεν υπάρχουν στη Ναυτεμπορική)
REALTIME_URL = "https://www.naftemporiki.gr/chrimatistirio/real-time/"
REALTIME_MIN_ROWS = 20      # λιγότερες γραμμές = αποτυχία ανάγνωσης, αγνοούμε

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

DATA_DIR = os.path.join(os.path.expanduser("~"), ".xa_screener")
PORTFOLIO_FILE = os.path.join(DATA_DIR, "portfolio.json")


# ---------------------------------------------------------------------------
# Λήψη
# ---------------------------------------------------------------------------

def fetch_html(url, timeout=25):
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "el-GR,el;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, identity",
    })
    with urllib.request.urlopen(req, timeout=timeout,
                                context=ssl.create_default_context()) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding", "").lower() == "gzip":
            raw = gzip.decompress(raw)
    return raw.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Ανάγνωση HTML
# ---------------------------------------------------------------------------

class _TableParser(HTMLParser):
    """Βγάζει όλους τους <table> ως λίστες από γραμμές/κελιά."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self._stack = []
        self._row = None
        self._cell = None

    def _flush_cell(self):
        if self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
        self._cell = None

    def _flush_row(self):
        self._flush_cell()
        if self._row is not None and self._stack:
            self._stack[-1].append(self._row)
        self._row = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._flush_row()
            self._stack.append([])
        elif tag == "tr":
            self._flush_row()
            self._row = []
        elif tag in ("td", "th"):
            self._flush_cell()
            if self._row is None:
                self._row = []
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            self._flush_cell()
        elif tag == "tr":
            self._flush_row()
        elif tag == "table":
            self._flush_row()
            if self._stack:
                self.tables.append(self._stack.pop())

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def close(self):
        super().close()
        self._flush_row()
        while self._stack:
            self.tables.append(self._stack.pop())


_TAG_RE = re.compile(r"<[^>]+>")
_NUM_RE = re.compile(r"[-+]?\d[\d\.]*(?:,\d+)?")


def parse_number(text):
    """'1.234,56' -> 1234.56 · '' -> None · '-0,45 %' -> -0.45"""
    if text is None:
        return None
    t = str(text).replace("\xa0", " ").replace("%", "").replace("€", "").strip()
    if not t or t in ("-", "--"):
        return None
    m = re.search(r"[-+]?[\d\.]*\d(?:,\d+)?", t)
    if not m:
        return None
    try:
        return float(m.group(0).replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _norm_header(text):
    return " ".join(text.replace(".", " ").replace("%", " ").split()).upper()


def _map_columns(header_row):
    idx = {}
    for i, cell in enumerate(header_row):
        h = _norm_header(cell)
        if not h:
            continue
        if h.startswith("ΣΥΜΒ") and "symbol" not in idx:
            idx["symbol"] = i
        elif h == "ΤΙΜΗ" and "price" not in idx:
            idx["price"] = i
        elif h.startswith("ΔΙΑΦ") and "diff" not in idx:
            idx["diff"] = i
        elif h.startswith("ΜΕΤ") and "change" not in idx:
            idx["change"] = i
        elif h.startswith("ΑΓΟΡΑ") and "bid" not in idx:
            idx["bid"] = i
        elif h.startswith("ΠΩΛΗΣΗ") and "ask" not in idx:
            idx["ask"] = i
        elif h.startswith("ΣΥΝ") and "ΟΓΚ" in h and "totvol" not in idx:
            idx["totvol"] = i
        elif h.startswith("ΟΓΚΟΣ") and "vol" not in idx:
            idx["vol"] = i
        elif h.startswith("ΩΡΑ") and "time" not in idx:
            idx["time"] = i
    if {"symbol", "price", "change"} <= set(idx):
        return idx
    return None


def parse_quotes(html):
    """Λίστα με dicts: symbol, price, diff, change, bid, ask, totvol, vol, time."""
    p = _TableParser()
    p.feed(html)
    p.close()

    best_rows = best_idx = None
    best_len = 0
    for table in p.tables:
        for row in table[:3]:
            idx = _map_columns(row)
            if idx and len(table) > best_len:
                best_rows, best_idx, best_len = table, idx, len(table)
                break
    if not best_rows:
        raise ValueError("Δεν βρέθηκε ο πίνακας τιμών - ίσως άλλαξε η δομή του site.")

    out, seen = [], set()
    for row in best_rows:
        if len(row) <= best_idx["change"]:
            continue
        sym = row[best_idx["symbol"]].strip()
        if not sym or _norm_header(sym).startswith("ΣΥΜΒ"):
            continue
        price = parse_number(row[best_idx["price"]])
        if price is None or sym.upper() in seen:
            continue
        seen.add(sym.upper())

        def cell(name):
            i = best_idx.get(name)
            return row[i].strip() if i is not None and i < len(row) else ""

        out.append({
            "symbol": sym,
            "price": price,
            "diff": parse_number(cell("diff")) or 0.0,
            "change": parse_number(cell("change")) or 0.0,
            "bid": cell("bid"),
            "ask": cell("ask"),
            "totvol": parse_number(cell("totvol")) or 0.0,
            "vol": parse_number(cell("vol")) or 0.0,
            "time": cell("time"),
        })
    if not out:
        raise ValueError("Ο πίνακας βρέθηκε αλλά δεν διαβάστηκε καμία μετοχή.")
    return out


def parse_quote_page(page, title=""):
    """Σελίδα /finance/quote/<σύμβολο>/ -> value, diff, change, time, turnover."""
    text = " ".join(_TAG_RE.sub(" ", unescape(page.replace("&nbsp;", " "))).split())
    m_upd = re.search(r"Τελ\.?\s*Ενημέρωση\s*(\d{1,2}:\d{2})", text)
    if not m_upd:
        return None
    head = text[max(0, m_upd.start() - 220):m_upd.start()]

    m = None
    for m in re.finditer(
            r"([\d\.]*\d,\d+)\s+([-+]?[\d\.]*\d,\d+)\s*\(\s*([-+]?[\d\.]*\d,\d+)\s*%\s*\)",
            head):
        pass
    if m is None:
        return None
    m_tz = re.search(r"Τζίρος\s*([\d\.]*\d)\s*€", text)
    return {
        "name": title,
        "value": parse_number(m.group(1)),
        "diff": parse_number(m.group(2)),
        "change": parse_number(m.group(3)),
        "time": m_upd.group(1),
        "turnover": m_tz.group(1) if m_tz else "",
    }


def parse_index(page, label="ΓΕΝΙΚΟΣ ΔΕΙΚΤΗΣ"):
    """Ο ΓΔ όπως εμφανίζεται στην κορυφή κάθε σελίδας (εφεδρική πηγή)."""
    pos = page.find(label)
    if pos < 0:
        return None
    chunk = unescape(page[pos:pos + 900].replace("&nbsp;", " "))
    text = " ".join(_TAG_RE.sub(" ", chunk).split())

    m_time = re.search(r"\b(\d{1,2}:\d{2})\b", text)
    time_s = m_time.group(1) if m_time else ""
    rest = text[m_time.end():] if m_time else text[len(label):]

    turnover = ""
    m_tz = re.search(r"Τζίρος[:\s]*([\d\.,]+\s*[^\s]*)", rest)
    if m_tz:
        turnover = " ".join(m_tz.group(1).split())
        rest = rest[:m_tz.start()]

    nums = [n for n in (parse_number(x) for x in _NUM_RE.findall(rest)) if n is not None]
    if not nums:
        return None
    return {
        "name": label, "time": time_s, "value": nums[0],
        "change": nums[1] if len(nums) > 1 else None,
        "diff": nums[2] if len(nums) > 2 else None,
        "turnover": turnover,
    }


def fetch_index(symbol, title=""):
    url = QUOTE_URL.format(urllib.parse.quote(symbol, safe=""))
    return parse_quote_page(fetch_html(url), title)


# ---------------------------------------------------------------------------
# Τιμές πραγματικού χρόνου (Ναυτεμπορική)
# ---------------------------------------------------------------------------

# Η κάθε γραμμή τελειώνει με: τιμή, διαφορά, μεταβολή%, ημερομηνία, ώρα,
# προηγούμενο κλείσιμο. Προσοχή: εδώ οι αριθμοί έχουν ΤΕΛΕΙΑ ως υποδιαστολή
# (4.4950), σε αντίθεση με το capital.gr που έχει κόμμα (4,4950).
_RT_TAIL = re.compile(
    r"(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s*%\s*"
    r"(\d{2}/\d{2}/\d{4})\s*,?\s*(\d{1,2}:\d{2})\s*Πρ\.?\s*Κλείσιμο\s*(-?\d+(?:\.\d+)?)"
)
_RT_SYMBOL = re.compile(r"^[A-ZΑ-ΩΆΈΉΊΌΎΏΪΫ0-9_&/.-]{1,16}$")


def _rt_float(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def parse_realtime(page):
    """Διαβάζει τη σελίδα πραγματικού χρόνου.

    Επιστρέφει dict: σύμβολο -> {price, diff, change, time, date, prev}
    Περιέχει μαζί μετοχές ΧΑ, μετοχές ΧΑΚ και όλους τους δείκτες.
    """
    text = " ".join(_TAG_RE.sub(" ", unescape(page.replace("&nbsp;", " "))).split())
    out = {}
    for part in text.split("ΑΝΑΛΥΤΙΚΑ"):
        tokens = part.split()
        if not tokens:
            continue
        symbol = tokens[0].strip()
        if not _RT_SYMBOL.match(symbol):
            continue
        match = None
        for match in _RT_TAIL.finditer(part):
            pass                                # κρατάμε το τελευταίο ταίριασμα
        if match is None:
            continue
        price = _rt_float(match.group(1))
        if price is None:
            continue
        out[symbol.upper()] = {
            "price": price,
            "diff": _rt_float(match.group(2)) or 0.0,
            "change": _rt_float(match.group(3)) or 0.0,
            "date": match.group(4),
            "time": match.group(5),
            "prev": _rt_float(match.group(6)),
        }
    return out


def fetch_realtime():
    """Κατεβάζει και διαβάζει τις τιμές πραγματικού χρόνου. {} σε αποτυχία."""
    try:
        data = parse_realtime(fetch_html(REALTIME_URL))
    except Exception:                                  # noqa: BLE001
        return {}
    return data if len(data) >= REALTIME_MIN_ROWS else {}


_last_indices = {}


def fetch_market(market_key="el", with_indices=True, realtime=True):
    """Κατεβάζει το ταμπλώ και τους δείκτες. Επιστρέφει (quotes, indices).

    Με realtime=True (προεπιλογή) οι τιμές έρχονται από τη Ναυτεμπορική σε
    πραγματικό χρόνο και συμπληρώνονται με όγκους/εντολές από το capital.gr.
    Κάθε μετοχή έχει πεδίο "rt": True αν η τιμή της είναι πραγματικού χρόνου.
    """
    market = MARKETS[market_key]
    html = fetch_html(market["url"])
    quotes = parse_quotes(html)

    rt = fetch_realtime() if realtime else {}

    # --- συγχώνευση: τιμή σε πραγματικό χρόνο, όγκος από το ταμπλώ ----------
    for q in quotes:
        live = rt.get(q["symbol"].upper())
        if live:
            q.update(price=live["price"], diff=live["diff"],
                     change=live["change"], time=live["time"],
                     prev=live.get("prev"), rt=True)
        else:
            q["rt"] = False

    indices = []
    if with_indices:
        for symbol, title in market["indices"]:
            data = None
            live = rt.get(symbol.upper())
            if live:
                data = {"name": title, "value": live["price"],
                        "diff": live["diff"], "change": live["change"],
                        "time": live["time"], "turnover": "", "rt": True}
            if data is None:
                try:
                    data = fetch_index(symbol, title)
                except Exception:                      # noqa: BLE001
                    data = None
            if data is None and symbol == "ΓΔ":
                try:
                    data = parse_index(html)            # εφεδρεία: κορυφή σελίδας
                    if data:
                        data["name"] = title
                except Exception:                      # noqa: BLE001
                    data = None
            if data:
                data.setdefault("rt", False)
                _last_indices[symbol] = data
            else:
                data = _last_indices.get(symbol)
            indices.append(dict(data, title=title) if data else {"title": title})
    return quotes, indices


def realtime_share(quotes):
    """Πόσες από τις μετοχές έχουν τιμή πραγματικού χρόνου (πλήθος, σύνολο)."""
    live = sum(1 for q in quotes if q.get("rt"))
    return live, len(quotes)


# ---------------------------------------------------------------------------
# Μορφοποίηση
# ---------------------------------------------------------------------------

def fmt(value, decimals=4):
    if value is None:
        return ""
    return f"{value:,.{decimals}f}".replace(",", "@").replace(".", ",").replace("@", ".")


def fmt_int(value):
    return "" if value is None else f"{int(value):,}".replace(",", ".")


def fmt_compact(value):
    """1732876 -> '1,7 εκ.' · 45867 -> '45,9 χιλ.'"""
    if not value:
        return "—"
    if value >= 1_000_000:
        return fmt(value / 1_000_000, 1) + " εκ."
    if value >= 1_000:
        return fmt(value / 1_000, 1) + " χιλ."
    return fmt_int(value)


# ---------------------------------------------------------------------------
# Χαρτοφυλάκιο
# ---------------------------------------------------------------------------

class Portfolio:
    def __init__(self, path=PORTFOLIO_FILE):
        self.path = path
        self._lock = threading.Lock()
        self.positions = []
        self.load()

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                self.positions = json.load(fh).get("positions", [])
        except (OSError, ValueError):
            self.positions = []

    def save(self):
        with self._lock:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"positions": self.positions,
                           "saved": datetime.now().isoformat(timespec="seconds")},
                          fh, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)

    def add(self, symbol, qty, cost, note=""):
        symbol = symbol.strip().upper()
        for p in self.positions:
            if p["symbol"] == symbol:
                total = p["qty"] + qty
                if total <= 0:
                    return
                p["cost"] = (p["qty"] * p["cost"] + qty * cost) / total
                p["qty"] = total
                if note:
                    p["note"] = note
                self.save()
                return
        self.positions.append({
            "symbol": symbol, "qty": qty, "cost": cost, "note": note,
            "date": datetime.now().strftime("%d/%m/%Y"),
        })
        self.save()

    def update(self, symbol, qty, cost, note=""):
        for p in self.positions:
            if p["symbol"] == symbol.upper():
                p["qty"], p["cost"], p["note"] = qty, cost, note
                self.save()
                return True
        return False

    def remove(self, symbol):
        n = len(self.positions)
        self.positions = [p for p in self.positions if p["symbol"] != symbol.upper()]
        if len(self.positions) != n:
            self.save()
            return True
        return False

    def clear(self):
        self.positions = []
        self.save()


def portfolio_rows(positions, quotes_by_symbol):
    """Υπολογίζει αξία, Κ/Ζ και βαρύτητα. Επιστρέφει (γραμμές, σύνολα)."""
    rows, total_value, total_cost = [], 0.0, 0.0
    for p in positions:
        q = quotes_by_symbol.get(p["symbol"].upper())
        price = q["price"] if q else None
        invested = p["qty"] * p["cost"]
        value = p["qty"] * price if price is not None else None
        pl = value - invested if value is not None else None
        total_cost += invested
        if value is not None:
            total_value += value
        rows.append({
            "symbol": p["symbol"], "qty": p["qty"], "cost": p["cost"],
            "note": p.get("note", ""), "price": price, "invested": invested,
            "value": value, "pl": pl,
            "plpct": (pl / invested * 100) if (pl is not None and invested) else None,
        })
    for r in rows:
        r["weight"] = (r["value"] / total_value * 100) if (r["value"] and total_value) else None
    total_pl = total_value - total_cost
    totals = {
        "value": total_value, "cost": total_cost, "pl": total_pl,
        "plpct": (total_pl / total_cost * 100) if total_cost else 0.0,
        "count": len(rows),
    }
    return rows, totals
