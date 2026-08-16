"""Minimalist Gradio UI for viewing the CTD Commons dataset."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

try:
    import gradio as gr
    import pandas as pd
except ImportError:
    gr = None
    pd = None

logger = logging.getLogger(__name__)

COL_ACC = "Id"
COL_DRUG = "Rx"
COL_NAME = "Name"
COL_TYPE = "Ext"
COL_SIZE = "Size"
COL_WEB = "🌐"
COL_LOCAL = "↗️"

ALL_COLS = [COL_ACC, COL_DRUG, COL_NAME, COL_TYPE, COL_SIZE, COL_WEB, COL_LOCAL]

CSS = """
.resizable-table table {
    table-layout: auto !important;
    width: 100% !important;
}
.resizable-table th, .resizable-table td {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    resize: horizontal;
}
.resizable-table th {
    font-weight: 600;
}
"""


def _fmt_size(nbytes: float) -> str:
    if pd.isna(nbytes):
        return ""
    n = int(nbytes)
    if n < 1024:
        return f"{n} B"
    if n < 1024**2:
        return f"{n / 1024:.1f} K"
    if n < 1024**3:
        return f"{n / 1024**2:.1f} M"
    return f"{n / 1024**3:.2f} G"


def _filter_data(
    df,
    search_text: str,
    selected_acc: str,
    selected_drug: str,
    selected_cols: list[str],
):
    filtered = df
    if selected_acc != "All":
        filtered = filtered[filtered["accession"] == selected_acc]
    if selected_drug != "All":
        filtered = filtered[filtered["drug"] == selected_drug]
    if search_text:
        mask = filtered["name"].str.contains(search_text, case=False, na=False)
        mask |= filtered["source_path"].str.contains(search_text, case=False, na=False)
        filtered = filtered[mask]

    filtered = filtered.head(1000).copy()

    if filtered.empty:
        return pd.DataFrame(columns=selected_cols), filtered

    filtered[COL_ACC] = filtered["accession"]
    filtered[COL_DRUG] = filtered["drug"]
    filtered[COL_NAME] = filtered["name"]
    filtered[COL_TYPE] = filtered["media_type"]
    filtered[COL_SIZE] = filtered["size_bytes"].apply(_fmt_size)
    filtered[COL_WEB] = filtered["source_url"].apply(lambda u: f"[link]({u})")
    filtered[COL_LOCAL] = "open"

    return filtered[selected_cols], filtered


def _open_file(
    evt: gr.SelectData, disp_df: pd.DataFrame, full_df: pd.DataFrame, root_str: str
) -> None:
    if disp_df.columns[evt.index[1]] != COL_LOCAL:
        return

    try:
        rel_path = full_df.iloc[evt.index[0]]["source_path"]
        full_path = Path(root_str) / rel_path
        if not full_path.exists():
            gr.Warning(f"Not downloaded: {full_path.name} (run `ctd get`)")
            return

        if sys.platform == "win32":
            os.startfile(full_path)
        elif sys.platform == "darwin":
            subprocess.run(["open", str(full_path)], check=False)
        else:
            subprocess.run(["xdg-open", str(full_path)], check=False)

        gr.Info(f"Opened {full_path.name}")
    except Exception as e:
        gr.Warning(f"Failed to open: {e}")


def create_app(parquet_path: Path, root: Path):
    if gr is None or pd is None:
        raise RuntimeError(
            "Gradio and pandas are required. Install with `uv sync --extra ui`"
        )

    if not parquet_path.exists():
        with gr.Blocks() as app:
            gr.Markdown(f"# CTD Commons\nDataset not found at `{parquet_path}`.")
        return app

    df = pd.read_parquet(parquet_path)
    accessions = ["All"] + sorted(df["accession"].dropna().unique().tolist())
    drugs = ["All"] + sorted(df["drug"].dropna().unique().tolist())

    with gr.Blocks(title="CTD Commons Viewer") as app:
        gr.Markdown(
            "# CTD Commons Dataset Viewer\n"
            "Select columns below. Click **open** in the **↗️** column to open "
            "a file with your system viewer (requires running `ctd get` first)."
        )

        with gr.Row():
            search_box = gr.Textbox(
                label="Search", placeholder="e.g. CSR, protocol, .pdf", scale=2
            )
            acc_dropdown = gr.Dropdown(
                choices=accessions, value="All", label="Accession", scale=1
            )
            drug_dropdown = gr.Dropdown(
                choices=drugs, value="All", label="Drug", scale=1
            )

        col_picker = gr.CheckboxGroup(
            choices=ALL_COLS, value=ALL_COLS, label="Display Columns"
        )

        initial_disp, initial_full = _filter_data(df, "", "All", "All", ALL_COLS)
        full_state = gr.State(initial_full)
        root_state = gr.State(str(root))

        data_grid = gr.Dataframe(
            value=initial_disp,
            interactive=False,
            wrap=True,
            datatype="markdown",
            elem_classes="resizable-table",
        )

        inputs = [search_box, acc_dropdown, drug_dropdown, col_picker]
        outputs = [data_grid, full_state]

        def filter_fn(s, a, d, c):
            return _filter_data(df, s, a, d, c)

        for comp in [search_box, acc_dropdown, drug_dropdown, col_picker]:
            comp.change(fn=filter_fn, inputs=inputs, outputs=outputs)

        data_grid.select(fn=_open_file, inputs=[data_grid, full_state, root_state])

    return app


def launch(
    parquet_path: Path, root: Path, share: bool = False, server_port: int = 7860
) -> None:
    app = create_app(parquet_path, root)
    app.launch(share=share, server_port=server_port, css=CSS)
