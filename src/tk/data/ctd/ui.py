"""Gradio viewer for the CTD Commons document register."""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import quote

import gradio as gr
import pandas as pd

logger = logging.getLogger(__name__)

COL_ACC = "Accession"
COL_DRUG = "Drug"
COL_NAME = "Document"
COL_FOLDER = "Folder"
COL_TYPE = "Type"
COL_SIZE = "KB"
COL_WEB = "↗"
COL_FILE = "⇥"

# Relative column widths, normalised to percentages for whatever subset is shown.
COL_WIDTHS = {
    COL_ACC: 12,
    COL_DRUG: 10,
    COL_NAME: 35,
    COL_FOLDER: 18,
    COL_TYPE: 8,
    COL_SIZE: 7,
    COL_WEB: 5,
    COL_FILE: 5,
}
ALL_COLS = list(COL_WIDTHS)
DEFAULT_COLS = [c for c in ALL_COLS if c != COL_ACC]

# Only the glyph columns hold links; everything else stays literal so that
# underscores and brackets in file names are not eaten by the markdown renderer.
MARKDOWN_COLS = {COL_WEB, COL_FILE}

PAGE_SIZES = ["25", "50", "100", "250"]
DEFAULT_PAGE_SIZE = "50"

ABSENT = "·"
PREV, NEXT = "◀", "▶"

CSS = """
:root {
    --ctd-ink: #16181a;
    --ctd-rule: #e6e4df;
    --ctd-muted: #8b8880;
    --ctd-accent: #0b6b5f;
}
.dark {
    --ctd-ink: #e8e6e1;
    --ctd-rule: #2b2d2b;
    --ctd-muted: #868a87;
    --ctd-accent: #4fbfa8;
}
/* Gradio clips the container, which silently disables position: sticky. */
.gradio-container {
    max-width: 1560px !important;
    padding-top: 0 !important;
    overflow: visible !important;
}
.gradio-container .gap { gap: 6px !important; }

/* Controls stay put while the page scrolls under them. flex: 0 0 auto stops
   the column absorbing the leftover height of its flex parent. */
.ctd-head {
    position: sticky;
    top: 0;
    z-index: 30;
    flex: 0 0 auto !important;
    background: var(--body-background-fill);
    padding: 8px 0 6px;
    border-bottom: 1px solid var(--ctd-rule);
    gap: 6px !important;
}
.ctd-head > * { flex: 0 0 auto !important; }

.ctd-eyebrow p {
    font-size: 11px;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--ctd-muted);
    margin: 0;
}
.ctd-count p {
    font-size: 12px;
    letter-spacing: 0.02em;
    color: var(--ctd-muted);
    margin: 0;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
}
.ctd-bar { align-items: center !important; gap: 4px !important; flex-wrap: nowrap; }
/* Keep Gradio's zero flex-basis: an auto basis collapses the block's width and
   wraps the one-line summary into a tall column. */
.ctd-bar > .ctd-count { flex: 1 1 0% !important; min-width: 200px !important; }
/* Gradio's `div.svelte-x > *` rule outranks a bare class, so these are scoped
   through .ctd-bar to win specificity and stay at their natural width. */
.ctd-bar > .ctd-step {
    flex: 0 0 34px !important;
    min-width: 34px !important;
    max-width: 34px !important;
    padding: 3px 0 !important;
    font-size: 11px;
    border-radius: 0 !important;
}
.ctd-bar > .ctd-page-no {
    flex: 0 0 58px !important;
    min-width: 58px !important;
    max-width: 58px !important;
}
.ctd-page-no p {
    font-size: 12px;
    color: var(--ctd-muted);
    margin: 0;
    text-align: center;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
}
.ctd-bar > .ctd-size {
    flex: 0 0 72px !important;
    min-width: 72px !important;
    max-width: 72px !important;
}
.ctd-size input { font-size: 12px !important; text-align: right; }

/* One thin line of column toggles, no card around them. */
.ctd-cols { gap: 0 !important; }
.ctd-cols label {
    font-size: 11px !important;
    padding: 1px 7px !important;
    border-radius: 0 !important;
    letter-spacing: 0.04em;
}
.ctd-cols input[type="checkbox"] { width: 12px !important; height: 12px !important; }

.ctd-legend { padding-top: 4px; }

/* Filters read as ruled blanks rather than boxed widgets. */
.ctd-filters, .ctd-filters .block, .ctd-filters .form {
    border: none !important;
    box-shadow: none !important;
    background: transparent !important;
    align-items: flex-end !important;
}
.ctd-filters label > span,
.ctd-filters span[data-testid="block-info"] {
    font-size: 10px !important;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--ctd-muted) !important;
}
.ctd-filters input,
.ctd-filters .wrap-inner,
.ctd-filters .secondary-wrap {
    border-radius: 0 !important;
}

.ctd-table { margin-top: 0 !important; border: none !important; }
.ctd-table > .block, .ctd-table .table-wrap { border-radius: 0 !important; }
.ctd-table table { font-size: 13px; font-variant-numeric: tabular-nums; }
.ctd-table .cell-wrap {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    min-height: 0 !important;
    line-height: 1.4;
}
.ctd-table th {
    font-size: 10px !important;
    font-weight: 500 !important;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--ctd-muted) !important;
}
.ctd-table td, .ctd-table th { padding: 2px 10px !important; }
.ctd-table td .cell-wrap { padding: 0 !important; }
.ctd-table td { border-color: var(--ctd-rule) !important; }
/* The glyph rail is the only colour in the table. */
.ctd-table a { color: var(--ctd-accent); text-decoration: none; font-size: 15px; }
.ctd-table a:hover { text-decoration: underline; }
"""


def _widths(cols: list[str]) -> list[str]:
    total = sum(COL_WIDTHS[c] for c in cols)
    return [f"{COL_WIDTHS[c] / total * 100:.4g}%" for c in cols]


def _datatypes(cols: list[str]) -> list[str]:
    return [
        "markdown" if c in MARKDOWN_COLS else "number" if c == COL_SIZE else "str"
        for c in cols
    ]


def _prepare(df, root: Path):
    """Derive the display columns once, at load, so filtering stays vectorised."""
    out = df.copy()
    out[COL_ACC] = out["accession"]
    out[COL_DRUG] = out["drug"]
    out[COL_NAME] = out["name"]
    out[COL_FOLDER] = out["parents"].map(lambda p: " / ".join(p) if len(p) else "—")
    out[COL_TYPE] = out["media_type"]
    out[COL_SIZE] = (out["size_bytes"] / 1024).round().astype("int64")
    out[COL_WEB] = "[" + COL_WEB + "](" + out["source_url"] + ")"

    # Absolute, percent-encoded so that spaces and parentheses in the ~3k paths
    # survive both the markdown link syntax and the file route.
    abs_paths = out["source_path"].map(lambda p: (root / p).resolve())
    out["_abs"] = abs_paths
    out["_haystack"] = (
        out["accession"]
        + " "
        + out["drug"]
        + " "
        + out["name"]
        + " "
        + out["source_path"]
    ).str.lower()
    return out


def _file_links(abs_paths) -> list[str]:
    """Link only files that are actually on disk; the rest get a muted dot."""
    return [
        f"[{COL_FILE}](/gradio_api/file={quote(str(p))})" if p.exists() else ABSENT
        for p in abs_paths
    ]


def _fmt_bytes(nbytes: float) -> str:
    n = float(nbytes)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:,.0f} {unit}" if unit == "B" else f"{n:,.1f} {unit}"
        n /= 1024
    return ""


def _filter(prepared, search: str, acc: str, drug: str, media: str):
    rows = prepared
    if acc != "All":
        rows = rows[rows[COL_ACC] == acc]
    if drug != "All":
        rows = rows[rows[COL_DRUG] == drug]
    if media != "All":
        rows = rows[rows[COL_TYPE] == media]
    for token in (search or "").lower().split():
        # regex=False: names carry '(', '+' and '[' that would otherwise raise.
        rows = rows[rows["_haystack"].str.contains(token, regex=False, na=False)]
    return rows


def _paginate(rows, page: int, size: int):
    pages = max(1, -(-len(rows) // size))
    page = min(max(page, 0), pages - 1)
    return rows.iloc[page * size : (page + 1) * size], page, pages


def _summary(matched, total: int) -> str:
    if len(matched) == 0:
        return "No documents match. Clear a filter or shorten the search."
    size = _fmt_bytes(matched["size_bytes"].sum())
    return f"{len(matched):,} of {total:,} documents · {size}"


def create_app(parquet_path: Path, root: Path):
    if not parquet_path.exists():
        with gr.Blocks(title="CTD Commons") as app:
            gr.Markdown("CTD Commons", elem_classes="ctd-eyebrow")
            gr.Markdown(
                f"No manifest at `{parquet_path}`. Build one with `ctd export-hf`."
            )
        return app

    raw = pd.read_parquet(parquet_path)
    prepared = _prepare(raw, root)
    total = len(prepared)

    def options(col, by_frequency: bool = False):
        values = prepared[col].dropna()
        # Extensions are parsed from file names, so the long tail is noise like
        # "concomitant medications". Frequency order keeps pdf/sas7bdat on top.
        ordered = (
            values.value_counts().index.tolist()
            if by_frequency
            else sorted(set(values))
        )
        return ["All"] + ordered

    def render(search, acc, drug, media, size_label, cols, page):
        cols = [c for c in ALL_COLS if c in cols] or DEFAULT_COLS
        matched = _filter(prepared, search, acc, drug, media)
        shown, page, pages = _paginate(matched, int(page), int(size_label))

        view = pd.DataFrame(index=shown.index)
        for col in cols:
            # Presence on disk is checked per page, so it stays true after `ctd get`.
            view[col] = _file_links(shown["_abs"]) if col == COL_FILE else shown[col]

        table = gr.Dataframe(
            value=view,
            column_widths=_widths(cols),
            datatype=_datatypes(cols),
        )
        return (
            table,
            _summary(matched, total),
            page,
            f"{page + 1} / {pages:,}",
            gr.Button(interactive=page > 0),
            gr.Button(interactive=page + 1 < pages),
        )

    with gr.Blocks(title="CTD Commons", fill_width=True) as app:
        with gr.Column(elem_classes="ctd-head"):
            gr.Markdown("CTD Commons · document register", elem_classes="ctd-eyebrow")

            with gr.Row(elem_classes="ctd-filters"):
                search = gr.Textbox(
                    label="Search",
                    placeholder="Every term must appear in the name, folder or drug",
                    scale=4,
                )
                acc = gr.Dropdown(
                    options(COL_ACC), value="All", label="Accession", scale=1
                )
                drug = gr.Dropdown(
                    options(COL_DRUG), value="All", label="Drug", scale=1
                )
                media = gr.Dropdown(
                    options(COL_TYPE, by_frequency=True),
                    value="All",
                    label="Type",
                    scale=1,
                )
            # Inline rather than in a dropdown: 8 checkboxes fit on one line and
            # never push the sticky header taller.
            cols = gr.CheckboxGroup(
                ALL_COLS,
                value=DEFAULT_COLS,
                show_label=False,
                container=False,
                elem_classes="ctd-cols",
            )

            with gr.Row(elem_classes="ctd-bar"):
                summary = gr.Markdown(elem_classes="ctd-count")
                size = gr.Dropdown(
                    PAGE_SIZES,
                    value=DEFAULT_PAGE_SIZE,
                    show_label=False,
                    container=False,
                    scale=0,
                    min_width=64,
                    elem_classes="ctd-size",
                )
                prev = gr.Button(PREV, scale=0, min_width=34, elem_classes="ctd-step")
                pager = gr.Markdown(elem_classes="ctd-page-no")
                nxt = gr.Button(NEXT, scale=0, min_width=34, elem_classes="ctd-step")

        table = gr.Dataframe(
            interactive=False,
            wrap=False,
            max_height="72vh",
            show_search="none",
            buttons=[],  # the toolbar adds a ~30px bar directly above the table
            elem_classes="ctd-table",
        )
        gr.Markdown(
            f"{COL_WEB} source on archive.icosian.net · "
            f"{COL_FILE} local copy · {ABSENT} not downloaded yet, run `ctd get`",
            elem_classes="ctd-count ctd-legend",
        )

        page = gr.State(0)
        filters = [search, acc, drug, media, size, cols]
        outputs = [table, summary, page, pager, prev, nxt]

        def on_filter(*args):
            return render(*args, 0)  # a new result set always starts at page one

        def step(delta):
            return lambda *args: render(*args[:-1], int(args[-1]) + delta)

        for control in filters:
            # always_last coalesces keystrokes, so typing does not queue a
            # re-render of the whole table per character.
            control.change(
                on_filter,
                filters,
                outputs,
                show_progress="minimal",
                trigger_mode="always_last",
            )
        prev.click(step(-1), [*filters, page], outputs, show_progress="minimal")
        nxt.click(step(+1), [*filters, page], outputs, show_progress="minimal")
        app.load(on_filter, filters, outputs)

    return app


def launch(
    parquet_path: Path, root: Path, share: bool = False, server_port: int = 7860
) -> None:
    app = create_app(parquet_path, root)
    app.launch(
        share=share,
        server_port=server_port,
        css=CSS,
        allowed_paths=[str(root.resolve())],
    )
