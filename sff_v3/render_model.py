"""render_model.py — Render the SFF v2 model as a downloadable image (PNG + SVG).

Reads the live schema like generate_model.py, then draws it with Graphviz: HTML-like
record nodes (table header + column rows, PK/FK marked) and edges labelled with the
joining key. Layout is left-to-right so the raw anchor sits on the left and the
results fan out to the right.
USAGE: python render_model.py [ruta_db]
"""
import sys

import graphviz

from generate_model import RELATIONSHIPS, PRIMARY_KEYS, TABLE_NOTES, read_schema, normalize_type

DB_PATH = sys.argv[1] if len(sys.argv) > 1 else "salida/sff_v2_golden.db"
OUTPUT_STEM = "modelo/sff_v2_erd"
SKIP_COLUMNS = {"process_date", "execution_id"}          # traceability, not model
GROUP_COLOR = {                                          # by role in the pipeline
    "anchor": ("#E6F1FB", "#185FA5"), "bridge": ("#EEEDFE", "#534AB7"),
    "phase0": ("#F1EFE8", "#5F5E5A"), "phase1": ("#E1F5EE", "#0F6E56"),
    "phase2": ("#FAECE7", "#993C1D"), "phase3": ("#FBEAF0", "#993556"),
    "phase4": ("#FAEEDA", "#854F0B"), "audit":  ("#F1EFE8", "#5F5E5A")}
TABLE_GROUP = {
    "sff_fact_fine": "anchor", "sff_key_bridge": "bridge",
    "sff_fact_fu": "phase0", "sff_fu_summary": "phase0", "sff_lookup_fu": "phase0",
    "sff_lookup_comb": "phase0", "sff_fact_fu_gaps": "phase1",
    "sff_fs_summary": "phase1", "sff_support_chain": "phase1",
    "sff_parent_ladder": "phase1", "sff_diag_dinamica": "phase1",
    "sff_simpson_contrafactual": "phase1", "sff_uplift_chain": "phase2",
    "sff_forecast_detail": "phase3", "sff_forecast_bands": "phase4",
    "sff_backtest_pred": "phase4", "sff_backtest_pred_fu": "phase4",
    "sff_forecast_pred_fu": "phase4", "sff_forecast_seleccion": "phase4",
    "sff_rolling_next_month": "phase4", "sff_rolling_nm_resumen": "phase4",
    "sff_dim_tecnica": "phase4", "sff_horizon_report_series": "phase4",
    "sff_horizon_report_total": "phase4", "sff_validation_report": "audit"}


def build_label(table, columns, foreign_key_columns):
    fill, stroke = GROUP_COLOR[TABLE_GROUP.get(table, "audit")]
    rows = [f'<TR><TD BGCOLOR="{stroke}" ALIGN="CENTER">'
            f'<FONT COLOR="white" POINT-SIZE="13"><B>{table}</B></FONT></TD></TR>']
    if table in TABLE_NOTES:
        rows.append(f'<TR><TD BGCOLOR="{fill}" ALIGN="LEFT">'
                    f'<FONT POINT-SIZE="9" COLOR="{stroke}"><I>{TABLE_NOTES[table]}</I></FONT></TD></TR>')
    for column_name, column_type in columns:
        if column_name in SKIP_COLUMNS:
            continue
        marker = ""
        if PRIMARY_KEYS.get(table) == column_name:
            marker = " <B>PK</B>"
        elif (table, column_name) in foreign_key_columns:
            marker = " <B>FK</B>"
        rows.append(f'<TR><TD ALIGN="LEFT" PORT="{column_name}"><FONT POINT-SIZE="10">'
                    f'{column_name}  <FONT COLOR="#888780">{normalize_type(column_type)[1]}</FONT>'
                    f'{marker}</FONT></TD></TR>')
    return "<<TABLE BORDER='1' CELLBORDER='0' CELLSPACING='0' CELLPADDING='4' " \
           f"COLOR='{stroke}' BGCOLOR='white'>{''.join(rows)}</TABLE>>"


def build_compact_label(table):
    """Overview node: just the table name and its role — the map you present."""
    fill, stroke = GROUP_COLOR[TABLE_GROUP.get(table, "audit")]
    note = TABLE_NOTES.get(table, "")
    note_row = (f'<TR><TD ALIGN="CENTER"><FONT POINT-SIZE="9" COLOR="{stroke}">'
                f'{note[:38]}</FONT></TD></TR>') if note else ""
    return (f"<<TABLE BORDER='1' CELLBORDER='0' CELLSPACING='0' CELLPADDING='6' "
            f"COLOR='{stroke}' BGCOLOR='{fill}'>"
            f"<TR><TD ALIGN='CENTER'><FONT POINT-SIZE='13' COLOR='{stroke}'><B>{table}</B></FONT></TD></TR>"
            f"{note_row}</TABLE>>")


def render_compact(schema):
    diagram = graphviz.Digraph("sff_v2_compact", format="png")
    diagram.attr(rankdir="LR", splines="spline", nodesep="0.35", ranksep="1.9",
                 bgcolor="white", fontname="Helvetica", concentrate="true",
                 label="\nSFF v2 — mapa de tablas y relaciones (vista de conjunto)",
                 labelloc="t", fontsize="18")
    diagram.attr("node", shape="plaintext", fontname="Helvetica")
    diagram.attr("edge", color="#5F5E5A", fontname="Helvetica", fontsize="9", arrowsize="0.7")
    for table in schema:
        diagram.node(table, build_compact_label(table))
    for child, child_column, parent, parent_column in RELATIONSHIPS:
        if child in schema and parent in schema:
            diagram.edge(parent, child, label=child_column)
    diagram.render(OUTPUT_STEM + "_compacto", cleanup=True)
    diagram.format = "svg"
    diagram.render(OUTPUT_STEM + "_compacto", cleanup=True)


def main():
    schema = read_schema(DB_PATH)
    foreign_key_columns = {(child, column) for child, column, _, _ in RELATIONSHIPS}
    diagram = graphviz.Digraph("sff_v2", format="png")
    diagram.attr(rankdir="LR", splines="spline", concentrate="false", nodesep="0.45", ranksep="1.5",
                 bgcolor="white", fontname="Helvetica",
                 label="\\nSFF v2 — modelo de datos (25 tablas · el raw entra por la izquierda, "
                       "los resultados salen a la derecha)", labelloc="t", fontsize="18")
    diagram.attr("node", shape="plaintext", fontname="Helvetica")
    diagram.attr("edge", color="#5F5E5A", fontname="Helvetica", fontsize="9", arrowsize="0.7")
    for table, columns in schema.items():
        diagram.node(table, build_label(table, columns, foreign_key_columns))
    for child, child_column, parent, parent_column in RELATIONSHIPS:
        if child in schema and parent in schema:
            diagram.edge(f"{parent}:{parent_column}", f"{child}:{child_column}",
                         label=child_column, headlabel="n", taillabel="1",
                         labeldistance="1.6", labelfontsize="8")
    diagram.render(OUTPUT_STEM, cleanup=True)
    diagram.format = "svg"
    diagram.render(OUTPUT_STEM, cleanup=True)
    render_compact(schema)
    print(f"imágenes emitidas: {OUTPUT_STEM}[.png/.svg] (detalle con columnas) y "
          f"{OUTPUT_STEM}_compacto[.png/.svg] (vista de conjunto) · {len(schema)} tablas")


if __name__ == "__main__":
    main()
