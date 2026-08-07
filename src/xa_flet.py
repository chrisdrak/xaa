#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ΧΑ Screener - έκδοση Flet (Android / desktop)
=============================================

Δουλεύει και με Flet 1.0 / 0.80+ (νέο API) και με τις παλιότερες 0.2x.
Οι διαφορές των δύο API καλύπτονται από το τμήμα "συμβατότητα" παρακάτω:
ft.padding.only -> ft.Padding.only, ft.app -> ft.run,
ft.alignment.center -> ft.Alignment.CENTER, ft.dropdown.Option -> ft.DropdownOption.

    pip install flet
    python xa_flet.py

Δημιουργία APK (θέλει Flutter SDK):

    pip install "flet[all]"
    flet build apk

Απαιτεί το αρχείο xa_core.py στον ίδιο φάκελο.
"""

import re
import threading
import time

import flet as ft

import xa_core as C


# ===========================================================================
# Συμβατότητα ανάμεσα σε εκδόσεις του Flet
# ===========================================================================

def _pick(*names):
    """Το πρώτο attribute του ft που υπάρχει σε αυτή την έκδοση."""
    for n in names:
        v = getattr(ft, n, None)
        if v is not None:
            return v
    return None


def _has(obj, name):
    return obj is not None and hasattr(obj, name)


ICONS = _pick("Icons", "icons")
COLORS = _pick("Colors", "colors")

_Padding = _pick("Padding")
_padding_mod = getattr(ft, "padding", None)
_Margin = _pick("Margin")
_margin_mod = getattr(ft, "margin", None)
_Border = _pick("Border")
_border_mod = getattr(ft, "border", None)
BorderSide = _pick("BorderSide") or getattr(_border_mod, "BorderSide", None)

BUTTON_CLS = _pick("ElevatedButton", "Button", "FilledButton")
TEXTBUTTON_CLS = _pick("TextButton", "Button")
NAV_DEST = _pick("NavigationBarDestination", "NavigationDestination")

_BAD_KW = re.compile(r"unexpected keyword argument '([^']+)'")


def make(cls, *args, **kw):
    """Φτιάχνει control αγνοώντας παραμέτρους που δεν υποστηρίζει η
    εγκατεστημένη έκδοση, αντί να σκάει η εφαρμογή."""
    while True:
        try:
            return cls(*args, **kw)
        except TypeError as exc:
            m = _BAD_KW.search(str(exc))
            if m and m.group(1) in kw:
                kw.pop(m.group(1))
                continue
            raise


def pad(left=0, top=0, right=0, bottom=0):
    if _has(_Padding, "only"):
        return _Padding.only(left=left, top=top, right=right, bottom=bottom)
    return _padding_mod.only(left=left, top=top, right=right, bottom=bottom)


def pad_sym(vertical=0, horizontal=0):
    if _has(_Padding, "symmetric"):
        return _Padding.symmetric(vertical=vertical, horizontal=horizontal)
    return _padding_mod.symmetric(vertical=vertical, horizontal=horizontal)


def margin_top(value):
    if _has(_Margin, "only"):
        return _Margin.only(top=value)
    return _margin_mod.only(top=value)


def border_bottom(width, color):
    side = BorderSide(width, color)
    if _has(_Border, "only"):
        return _Border.only(bottom=side)
    return _border_mod.only(bottom=side)


def align_center():
    A = _pick("Alignment")
    if _has(A, "CENTER"):
        return A.CENTER
    return getattr(ft, "alignment").center


def dropdown_option(key, text):
    cls = _pick("DropdownOption")
    if cls is not None:
        return make(cls, key=key, text=text)
    return ft.dropdown.Option(key, text)


def icon(*names):
    for n in names:
        v = getattr(ICONS, n, None)
        if v is not None:
            return v
    return None


def show(page, control):
    """Ανοίγει bottom sheet / snackbar σε οποιαδήποτε έκδοση."""
    for name in ("show_dialog", "open"):
        fn = getattr(page, name, None)
        if callable(fn):
            try:
                fn(control)
                return
            except Exception:                          # noqa: BLE001
                pass
    try:
        if control not in page.overlay:
            page.overlay.append(control)
        control.open = True
    except Exception:                                  # noqa: BLE001
        pass
    page.update()


def hide(page, control):
    for name in ("pop_dialog", "close"):
        fn = getattr(page, name, None)
        if callable(fn):
            try:
                fn(control)
                return
            except Exception:                          # noqa: BLE001
                pass
    try:
        control.open = False
    except Exception:                                  # noqa: BLE001
        pass
    page.update()


def run_app(target):
    fn = _pick("run")
    if fn is not None:
        return fn(target)
    return ft.app(target=target)


# ===========================================================================
# Χρώματα και μικρά βοηθητικά
# ===========================================================================

BG = "#12161c"
CARD = "#1a1f27"
LINE = "#252c36"
TXT = "#e8eaed"
DIM = "#8b95a5"
UP, UP_BG = "#3ddc84", "#12301f"
DN, DN_BG = "#ff6b6b", "#331717"
ACCENT, ON_ACCENT = "#6aa9ff", "#062044"

AUTO_REFRESH_SECONDS = 30      # πόσο συχνά ανανεώνονται οι τιμές


def col(v):
    return UP if (v or 0) > 0 else DN if (v or 0) < 0 else DIM


def chip_bg(v):
    return UP_BG if (v or 0) > 0 else DN_BG if (v or 0) < 0 else "#20262f"


def signed(v, d=2):
    return "—" if v is None else ("+" if v > 0 else "") + C.fmt(v, d)


def txt(value, size=14, color=TXT, bold=False):
    return make(ft.Text, str(value), size=size, color=color,
                weight=ft.FontWeight.W_500 if bold else ft.FontWeight.NORMAL)


def button(label, on_click, ghost=False, color=None):
    """Το κείμενο μπαίνει ως content, ώστε να μην επηρεάζει η μετονομασία
    text -> label στα κουμπιά του Flet 1.0."""
    cls = TEXTBUTTON_CLS if ghost else BUTTON_CLS
    kw = {"content": txt(label, 14, color or (DIM if ghost else ON_ACCENT),
                         bold=not ghost),
          "on_click": on_click}
    if not ghost:
        kw.update(bgcolor=ACCENT, width=420)
    return make(cls, **kw)


def field(label, value="", numeric=False, read_only=False):
    return make(ft.TextField, label=label, value=str(value), dense=True,
                color=TXT, border_color=LINE, text_size=14, read_only=read_only,
                keyboard_type=ft.KeyboardType.NUMBER if numeric else None)


def row(controls, spread=True, spacing=8):
    return make(ft.Row, controls, spacing=spacing,
                alignment=(ft.MainAxisAlignment.SPACE_BETWEEN if spread
                           else ft.MainAxisAlignment.START),
                vertical_alignment=ft.CrossAxisAlignment.CENTER)


def column(controls, spacing=2, end=False):
    return make(ft.Column, controls, spacing=spacing, tight=True,
                horizontal_alignment=(ft.CrossAxisAlignment.END if end
                                      else ft.CrossAxisAlignment.START))


# ===========================================================================
# Εφαρμογή
# ===========================================================================

class App:
    def __init__(self, page):
        self.page = page
        self.market = "el"
        self.tab = 0
        self.quotes = []
        self.indices = []
        self.portfolio = C.Portfolio()
        self.search = ""
        self.filters = {}
        self.loading = False
        self.closed = False
        self.updated = "—"
        self.live = (0, 0)

        page.title = "ΧΑ Screener"
        page.bgcolor = BG
        page.padding = 0
        try:
            page.theme_mode = ft.ThemeMode.DARK
        except Exception:                              # noqa: BLE001
            pass
        try:
            page.window.width, page.window.height = 400, 820
        except Exception:                              # noqa: BLE001
            try:
                page.window_width, page.window_height = 400, 820
            except Exception:                          # noqa: BLE001
                pass

        self._build()
        self.refresh()
        threading.Thread(target=self._auto_refresh, daemon=True).start()

    # -- δομή -------------------------------------------------------------
    def _build(self):
        self.title = txt("Μετοχές", 17, TXT, bold=True)
        self.market_btn = make(TEXTBUTTON_CLS, content=txt("ΧΑ", 13, DIM),
                               on_click=self.toggle_market)
        self.search_field = make(
            ft.TextField, hint_text="σύμβολο…", visible=False, dense=True,
            filled=True, bgcolor=CARD, border_color=LINE, color=TXT,
            text_size=14, on_change=self.on_search)

        self.idx_row = make(ft.Row, [], spacing=6, scroll=ft.ScrollMode.HIDDEN)
        self.idx_more = make(ft.Text, "", size=12, color=DIM, visible=False)

        actions = make(ft.Row, [
            make(ft.IconButton, icon=icon("SEARCH"), icon_color=DIM,
                 icon_size=20, on_click=self.toggle_search),
            make(ft.IconButton, icon=icon("TUNE", "FILTER_LIST"), icon_color=DIM,
                 icon_size=20, on_click=self.open_filters),
            self.market_btn,
        ], spacing=0)

        header = make(ft.Container, content=make(ft.Column, [
            row([self.title, actions]),
            self.search_field,
            make(ft.Container, content=self.idx_row, on_click=self.toggle_idx_more),
            self.idx_more,
        ], spacing=4, tight=True), padding=pad(14, 10, 8, 8), bgcolor=BG,
            border=border_bottom(1, LINE))

        self.body = make(ft.ListView, controls=[], expand=True, spacing=0, padding=0)
        self.status = txt("Φόρτωση…", 13, DIM)

        self.fab = make(ft.FloatingActionButton, icon=icon("ADD"), bgcolor=ACCENT,
                        foreground_color=ON_ACCENT, visible=False,
                        on_click=lambda e: self.position_dialog())

        self.nav = make(ft.NavigationBar, selected_index=0, bgcolor=CARD,
                        on_change=self.on_tab, destinations=[
                            make(NAV_DEST, icon=icon("LIST_ALT", "LIST"),
                                 label="Μετοχές"),
                            make(NAV_DEST, icon=icon("WORK_OUTLINE", "WORK"),
                                 label="Χαρτοφυλάκιο"),
                            make(NAV_DEST, icon=icon("INFO_OUTLINE", "INFO"),
                                 label="Πληροφορίες"),
                        ])

        self.page.add(make(ft.Column, [
            header,
            make(ft.Container, content=self.status, padding=pad(14, 6, 14, 0)),
            self.body,
        ], expand=True, spacing=0))
        for attr, value in (("floating_action_button", self.fab),
                            ("navigation_bar", self.nav)):
            try:
                setattr(self.page, attr, value)
            except Exception:                          # noqa: BLE001
                pass
        self.page.update()

    # -- λήψη -------------------------------------------------------------
    def refresh(self, e=None):
        if self.loading:
            return
        self.loading = True
        self.status.value = "Λήψη δεδομένων…"
        self.page.update()
        threading.Thread(target=self._worker, daemon=True).start()

    def _auto_refresh(self):
        """Ανανέωση κάθε AUTO_REFRESH_SECONDS, όσο η εφαρμογή είναι ανοιχτή."""
        while not self.closed:
            time.sleep(AUTO_REFRESH_SECONDS)
            if not self.closed:
                self.refresh()

    def _worker(self):
        try:
            self.quotes, self.indices = C.fetch_market(self.market)
            self.updated = time.strftime("%H:%M:%S")
            self.live = C.realtime_share(self.quotes)
            live, total = self.live
            mark = "πραγματικός χρόνος" if live else "καθυστέρηση 15'"
            self.status.value = f"{total} μετοχές · {mark} · {self.updated}"
        except Exception as exc:                       # noqa: BLE001
            self.status.value = f"Σφάλμα: {exc}"
        self.loading = False
        self.render()

    # -- ενέργειες --------------------------------------------------------
    def toggle_market(self, e):
        self.market = "cy" if self.market == "el" else "el"
        self.market_btn.content = txt(C.MARKETS[self.market]["short"], 13, DIM)
        self.quotes, self.indices = [], []
        self.body.controls.clear()
        self.refresh()

    def toggle_search(self, e):
        self.search_field.visible = not self.search_field.visible
        if not self.search_field.visible:
            self.search_field.value = ""
            self.search = ""
        self.render()

    def on_search(self, e):
        self.search = (e.control.value or "").strip().upper()
        self.render()

    def on_tab(self, e):
        self.tab = e.control.selected_index
        self.render()

    def toggle_idx_more(self, e):
        self.idx_more.visible = not self.idx_more.visible
        self.page.update()

    # -- εμφάνιση ---------------------------------------------------------
    def render(self):
        self.title.value = ["Μετοχές", "Χαρτοφυλάκιο", "Πληροφορίες"][self.tab]
        self.fab.visible = self.tab == 1
        self.render_indices()
        self.body.controls.clear()
        (self.render_stocks, self.render_portfolio, self.render_info)[self.tab]()
        self.page.update()

    def render_indices(self):
        parts, detail = [], []
        for i, ix in enumerate(self.indices):
            if i:
                parts.append(txt("·", 12, "#3a4750"))
            title = ix.get("title", "")
            if ix.get("value") is None:
                parts.append(txt(f"{title} —", 12, DIM))
                detail.append(f"{title}: μη διαθέσιμο")
                continue
            chg = ix.get("change")
            arrow = "▲" if (chg or 0) > 0 else "▼" if (chg or 0) < 0 else "■"
            parts += [txt(title, 12, DIM),
                      txt(C.fmt(ix["value"], 2), 12, TXT, bold=True),
                      txt(f"{arrow}{C.fmt(abs(chg or 0), 2)} %", 12, col(chg))]
            detail.append(
                f"{title}: {C.fmt(ix['value'], 2)} · {signed(ix.get('diff'))} μον."
                f" · {ix.get('time', '')}"
                + (f" · τζίρος {ix['turnover']} €" if ix.get("turnover") else ""))
        parts.append(txt("⌄", 12, DIM))
        self.idx_row.controls = parts
        self.idx_more.value = "\n".join(detail)

    def visible_quotes(self):
        f = self.filters
        out = []
        for q in self.quotes:
            if self.search and self.search not in q["symbol"].upper():
                continue
            if f.get("pmin") is not None and q["price"] < f["pmin"]:
                continue
            if f.get("pmax") is not None and q["price"] > f["pmax"]:
                continue
            if f.get("cmin") is not None and q["change"] < f["cmin"]:
                continue
            if f.get("cmax") is not None and q["change"] > f["cmax"]:
                continue
            if f.get("active") and not q["totvol"]:
                continue
            out.append(q)
        key = f.get("sort", "change")
        rev = f.get("dir", "desc") == "desc"
        if key == "symbol":
            out.sort(key=lambda r: r["symbol"], reverse=rev)
        else:
            out.sort(key=lambda r: r.get(key) or 0, reverse=rev)
        return out

    def list_row(self, content, on_click=None):
        return make(ft.Container, content=content, on_click=on_click,
                    padding=pad_sym(vertical=11, horizontal=14),
                    border=border_bottom(1, LINE))

    def chip(self, text, value):
        return make(ft.Container, content=txt(text, 11, col(value)),
                    bgcolor=chip_bg(value), border_radius=7,
                    padding=pad_sym(vertical=2, horizontal=7),
                    margin=margin_top(3))

    def empty(self, message):
        self.body.controls.append(make(
            ft.Container, content=txt(message, 14, DIM), padding=26,
            alignment=align_center()))

    def render_stocks(self):
        rows = self.visible_quotes()
        if not rows:
            self.empty("Καμία μετοχή με αυτά τα κριτήρια")
            return
        for q in rows:
            left = column([txt(q["symbol"], 15, TXT, bold=True),
                           txt(f"{q['time']} · {C.fmt_compact(q['totvol'])} τεμ.",
                               11, DIM)])
            right = column([txt(C.fmt(q["price"], 4), 15),
                            self.chip(f"{signed(q['change'])} %", q["change"])],
                           spacing=0, end=True)
            self.body.controls.append(self.list_row(
                row([left, right]),
                on_click=lambda e, x=q: self.stock_sheet(x)))

    def render_portfolio(self):
        by = {q["symbol"].upper(): q for q in self.quotes}
        rows, tot = C.portfolio_rows(self.portfolio.positions, by)

        self.body.controls.append(make(ft.Container, content=column([
            txt("Συνολική αξία", 12, DIM),
            txt(f"{C.fmt(tot['value'], 2)} €", 26, TXT, bold=True),
            txt(f"{signed(tot['pl'])} € · {signed(tot['plpct'])} % · "
                f"κόστος {C.fmt(tot['cost'], 2)} €", 13, col(tot["pl"])),
        ]), padding=14))

        if not rows:
            self.empty("Δεν έχεις θέσεις ακόμη. Πάτα + για να προσθέσεις.")
            return

        for r in rows:
            head = row([txt(r["symbol"], 15, TXT, bold=True),
                        txt("—" if r["value"] is None
                            else f"{C.fmt(r['value'], 2)} €", 15)])
            meta = row([txt(f"{C.fmt(r['qty'], 0)} τεμ. · κτήση "
                            f"{C.fmt(r['cost'], 4)}", 11, DIM),
                        self.chip("χωρίς τιμή" if r["pl"] is None else
                                  f"{signed(r['pl'])} € · {signed(r['plpct'])} %",
                                  r["pl"])])
            bar = make(ft.Container, bgcolor="#20262f", height=3,
                       border_radius=2, margin=margin_top(8),
                       content=make(ft.Container, bgcolor=ACCENT, height=3,
                                    border_radius=2,
                                    width=max(2.0, (r["weight"] or 0) * 2.6)))
            self.body.controls.append(self.list_row(
                column([head, meta, bar], spacing=4),
                on_click=lambda e, x=r: self.position_dialog(x)))

    def render_info(self):
        self.body.controls.append(make(ft.Container, content=column([
            txt("Τιμές σε πραγματικό χρόνο από τη Ναυτεμπορική.", 14),
            txt("Όγκοι και εντολές αγοράς/πώλησης από capital.gr (15' καθυστέρηση).",
                12, DIM),
            txt(f"Σε πραγματικό χρόνο: {self.live[0]} από {self.live[1]} μετοχές",
                13, DIM),
            txt(f"Αυτόματη ανανέωση κάθε {AUTO_REFRESH_SECONDS} δευτερόλεπτα", 13, DIM),
            txt(f"Αγορά: {C.MARKETS[self.market]['label']}", 13, DIM),
            txt(f"Τελευταία ενημέρωση: {self.updated}", 13, DIM),
            txt(f"Μετοχές στο ταμπλώ: {len(self.quotes)}", 13, DIM),
            txt(f"Θέσεις: {len(self.portfolio.positions)}", 13, DIM),
            make(ft.Container, height=10),
            button("Ανανέωση τώρα", self.refresh),
        ], spacing=6), padding=14))

    # -- φύλλα ------------------------------------------------------------
    def sheet(self, title, controls):
        inner = make(ft.Container, bgcolor=CARD, padding=16,
                     content=make(ft.Column,
                                  [txt(title, 16, TXT, bold=True)] + controls,
                                  spacing=10, tight=True))
        bs = make(ft.BottomSheet, content=inner, dismissible=True)
        show(self.page, bs)
        return bs

    def stock_sheet(self, q):
        def line(label, value, color=TXT):
            return row([txt(label, 13, DIM), txt(value, 13, color)])

        holder = {}

        def add(e):
            hide(self.page, holder["bs"])
            self.position_dialog(preset={"symbol": q["symbol"],
                                         "cost": q["price"]})

        holder["bs"] = self.sheet(q["symbol"], [
            line("Τιμή", C.fmt(q["price"], 4)),
            line("Μεταβολή", f"{signed(q['diff'])} · {signed(q['change'])} %",
                 col(q["change"])),
            line("Αγορά", q["bid"] or "—"),
            line("Πώληση", q["ask"] or "—"),
            line("Συν. όγκος", C.fmt_int(q["totvol"]) or "—"),
            line("Ώρα", q["time"] or "—"),
            button("Προσθήκη στο χαρτοφυλάκιο", add),
        ])

    def position_dialog(self, row_data=None, preset=None):
        edit = row_data is not None
        src = row_data or preset or {}
        f_sym = field("Σύμβολο", src.get("symbol", ""), read_only=edit)
        f_qty = field("Τεμάχια",
                      C.fmt(src["qty"], 0) if src.get("qty") else "", numeric=True)
        f_cost = field("Τιμή κτήσης",
                       C.fmt(src["cost"], 4) if src.get("cost") else "",
                       numeric=True)
        holder = {}

        def save(e):
            sym = (f_sym.value or "").strip().upper()
            qty = C.parse_number(f_qty.value)
            cost = C.parse_number(f_cost.value)
            if not sym or not qty or qty <= 0 or cost is None or cost < 0:
                self.toast("Συμπλήρωσε σύμβολο, τεμάχια και τιμή κτήσης.")
                return
            if edit:
                self.portfolio.update(sym, qty, cost)
            else:
                self.portfolio.add(sym, qty, cost)
            hide(self.page, holder["bs"])
            self.render()

        def delete(e):
            self.portfolio.remove(src.get("symbol", ""))
            hide(self.page, holder["bs"])
            self.render()

        controls = [f_sym, f_qty, f_cost, button("Αποθήκευση", save)]
        if edit:
            controls.append(button("Αφαίρεση θέσης", delete, ghost=True, color=DN))
        holder["bs"] = self.sheet("Επεξεργασία θέσης" if edit else "Νέα θέση",
                                  controls)

    def open_filters(self, e=None):
        f = self.filters

        def num_field(label, key):
            v = f.get(key)
            return field(label, "" if v is None else v, numeric=True)

        pmin, pmax = num_field("Τιμή από", "pmin"), num_field("έως", "pmax")
        cmin, cmax = num_field("Μετ. % από", "cmin"), num_field("έως", "cmax")
        active = make(ft.Checkbox, label="Μόνο με συναλλαγές",
                      value=f.get("active", False),
                      label_style=make(ft.TextStyle, color=TXT))
        sort = make(ft.Dropdown, label="Ταξινόμηση", value=f.get("sort", "change"),
                    color=TXT, border_color=LINE, dense=True, options=[
                        dropdown_option("change", "Μεταβολή %"),
                        dropdown_option("symbol", "Σύμβολο"),
                        dropdown_option("price", "Τιμή"),
                        dropdown_option("totvol", "Όγκος")])
        direction = make(ft.Dropdown, label="Σειρά", value=f.get("dir", "desc"),
                         color=TXT, border_color=LINE, dense=True, options=[
                             dropdown_option("desc", "φθίνουσα"),
                             dropdown_option("asc", "αύξουσα")])
        holder = {}

        def apply(e):
            self.filters = {
                "pmin": C.parse_number(pmin.value),
                "pmax": C.parse_number(pmax.value),
                "cmin": C.parse_number(cmin.value),
                "cmax": C.parse_number(cmax.value),
                "active": active.value, "sort": sort.value, "dir": direction.value,
            }
            hide(self.page, holder["bs"])
            self.render()

        def clear(e):
            self.filters = {}
            hide(self.page, holder["bs"])
            self.render()

        holder["bs"] = self.sheet("Φίλτρα", [
            row([pmin, pmax], spread=False),
            row([cmin, cmax], spread=False),
            row([sort, direction], spread=False),
            active,
            button("Εφαρμογή", apply),
            button("Καθαρισμός", clear, ghost=True),
        ])

    def toast(self, message):
        show(self.page, make(ft.SnackBar, content=txt(message, 14), bgcolor=CARD))


def main(page):
    App(page)


if __name__ == "__main__":
    run_app(main)
