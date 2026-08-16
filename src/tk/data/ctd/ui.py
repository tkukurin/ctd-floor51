"""Minimalist Gradio UI for viewing the CTD Commons dataset."""

from __future__ import annotations

import logging
from pathlib import Path

try:
    import gradio as gr
    import pandas as pd
except ImportError:
    gr = None
    pd = None

logger = logging.getLogger(__name__)


def _filter_data(df, search_text: str, selected_acc: str, selected_drug: str):
    filtered = df
    if selected_acc != "All":
        filtered = filtered[filtered["accession"] == selected_acc]
    if selected_drug != "All":
        filtered = filtered[filtered["drug"] == selected_drug]
    if search_text:
        mask = filtered["name"].str.contains(search_text, case=False, na=False)
        mask |= filtered["source_path"].str.contains(search_text, case=False, na=False)
        filtered = filtered[mask]
    return filtered.head(1000)


def create_app(parquet_path: Path):
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
        gr.Markdown("# CTD Commons Dataset Viewer")

        with gr.Row():
            search_box = gr.Textbox(
                label="Search", placeholder="e.g. CSR, protocol, .pdf"
            )
            acc_dropdown = gr.Dropdown(
                choices=accessions, value="All", label="Accession"
            )
            drug_dropdown = gr.Dropdown(choices=drugs, value="All", label="Drug")

        data_grid = gr.Dataframe(value=df.head(100), interactive=False)

        inputs = [search_box, acc_dropdown, drug_dropdown]

        def filter_fn(s, a, d):
            return _filter_data(df, s, a, d)

        search_box.change(fn=filter_fn, inputs=inputs, outputs=data_grid)
        acc_dropdown.change(fn=filter_fn, inputs=inputs, outputs=data_grid)
        drug_dropdown.change(fn=filter_fn, inputs=inputs, outputs=data_grid)

    return app


def launch(parquet_path: Path, share: bool = False, server_port: int = 7860) -> None:
    app = create_app(parquet_path)
    app.launch(share=share, server_port=server_port)
