"""generate_model.py — Emit the SFF v2 data model in three open, editable formats,
introspecting the ACTUAL database so the model can never drift from the code.

OUTPUTS (in ./modelo/):
  sff_v2_model.dbml  — dbdiagram.io / dbml-cli (edit + visual layout, open source)
  sff_v2_model.mmd   — Mermaid erDiagram (VS Code, mermaid.live, GitHub renders it)
  sff_v2_model.sql   — CREATE TABLE DDL with PK/FK, for DBeaver, SchemaSpy, pgModeler
USAGE: python generate_model.py [ruta_db]
"""
import os
import sqlite3
import sys

DB_PATH = sys.argv[1] if len(sys.argv) > 1 else "salida/sff_v2_golden.db"
OUTPUT_DIR = "modelo"

# ─── the relationship map: (child table, child column, parent table, parent column) ───
RELATIONSHIPS = [
    ("sff_fact_fine", "fu_comb_key", "sff_key_bridge", "fu_comb_key"),
    ("sff_fact_fine", "fu_key", "sff_fact_fu", "fu_key"),
    ("sff_fu_summary", "fu_key", "sff_fact_fu", "fu_key"),
    ("sff_key_bridge", "fs_key", "sff_fs_summary", "fs_key"),
    ("sff_support_chain", "fs_id", "sff_fs_summary", "fs_id"),
    ("sff_parent_ladder", "fs_id", "sff_fs_summary", "fs_id"),
    ("sff_key_bridge", "fs_id_L2", "sff_diag_dinamica", "fs_id_L2"),
    ("sff_backtest_pred", "fs_id_L2", "sff_diag_dinamica", "fs_id_L2"),
    ("sff_rolling_next_month", "fs_id_L2", "sff_diag_dinamica", "fs_id_L2"),
    ("sff_horizon_report_series", "fs_id_L2", "sff_diag_dinamica", "fs_id_L2"),
    ("sff_forecast_seleccion", "fs_id_L2", "sff_diag_dinamica", "fs_id_L2"),
    ("sff_key_bridge", "uplift_cell_key", "sff_uplift_chain", "uplift_cell_key"),
    ("sff_forecast_detail", "fu_key", "sff_fact_fu", "fu_key"),
    ("sff_forecast_bands", "fu_key", "sff_fact_fu", "fu_key"),
    ("sff_backtest_pred", "tecnica", "sff_dim_tecnica", "tecnica_id"),
    ("sff_forecast_seleccion", "tecnica_elegida", "sff_dim_tecnica", "tecnica_id"),
    ("sff_forecast_bands", "tecnica_id", "sff_dim_tecnica", "tecnica_id"),
    ("sff_rolling_next_month", "tecnica_id", "sff_dim_tecnica", "tecnica_id"),
    ("sff_backtest_pred_fu", "fu_key", "sff_fact_fu", "fu_key"),
    ("sff_forecast_pred_fu", "fu_key", "sff_fact_fu", "fu_key"),
    ("sff_lookup_fu", "fu_key", "sff_fact_fu", "fu_key"),
]
PRIMARY_KEYS = {
    "sff_fact_fine": "fu_comb_key", "sff_key_bridge": "fu_comb_key",
    "sff_fact_fu": "fu_key", "sff_fu_summary": "fu_key", "sff_fs_summary": "fs_key",
    "sff_diag_dinamica": "fs_id_L2", "sff_dim_tecnica": "tecnica_id",
    "sff_forecast_seleccion": "fs_id_L2", "sff_lookup_fu": "fu_key",
    "sff_lookup_comb": "comb_key",
}
TABLE_NOTES = {
    "sff_fact_fine": "El ancla: el raw con claves. Todo dinero se suma aquí.",
    "sff_key_bridge": "El pegamento: de una fila del raw a todos sus linajes.",
    "sff_fu_summary": "Referencia inmutable: error binomial peor caso por FU-mes.",
    "sff_fs_summary": "Salud de cada serie: soporte, huecos, moe en $.",
    "sff_support_chain": "Waterfall de reparacion: una fila por serie y etapa.",
    "sff_parent_ladder": "Escalera de padres: peldanos y el elegido.",
    "sff_diag_dinamica": "Gate y phi por pool: hay motor o es la moneda.",
    "sff_backtest_pred": "El juez: tecnica x horizonte x origen.",
    "sff_forecast_detail": "El forecast fila a fila.",
    "sff_forecast_bands": "La incertidumbre medida de cada fila del forecast.",
    "sff_validation_report": "Auditoria de la ejecucion: 17 checks.",
}
def normalize_type(raw_type: str) -> tuple:
    """Map any storage type name to (SQL DDL type, DBML type). Covers what pandas emits
    on sqlite (BIGINT/FLOAT/TEXT) and on SQL Server (nvarchar/float/bigint/datetime)."""
    lowered = (raw_type or "").lower()
    if any(token in lowered for token in ("int", "bool")):
        return "BIGINT", "bigint"
    if any(token in lowered for token in ("float", "real", "double", "numeric", "decimal")):
        return "FLOAT", "float"
    if "date" in lowered or "time" in lowered:
        return "DATETIME2", "datetime"
    return "NVARCHAR(255)", "varchar"


def read_schema(db_path):
    connection = sqlite3.connect(db_path)
    table_names = [row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'sff_%' ORDER BY name")]
    return {name: [(column[1], column[2].upper()) for column in
                   connection.execute(f"PRAGMA table_info([{name}])")] for name in table_names}


def write_dbml(schema, path):
    foreign_keys = {(child, column) for child, column, _, _ in RELATIONSHIPS}
    lines = ["// SFF v2 — modelo de datos. Abrir en https://dbdiagram.io (Import > DBML)",
             "// Regenerar con: python generate_model.py <ruta_db>", ""]
    for table, columns in schema.items():
        lines.append(f"Table {table} {{")
        for column_name, column_type in columns:
            settings = []
            if PRIMARY_KEYS.get(table) == column_name:
                settings.append("pk")
            if (table, column_name) in foreign_keys:
                settings.append("note: 'FK'")
            suffix = f" [{', '.join(settings)}]" if settings else ""
            lines.append(f"  {column_name} {normalize_type(column_type)[1]}{suffix}")
        if table in TABLE_NOTES:
            lines.append(f"  Note: '{TABLE_NOTES[table]}'")
        lines.append("}\n")
    for child, child_column, parent, parent_column in RELATIONSHIPS:
        if child in schema and parent in schema:
            lines.append(f"Ref: {child}.{child_column} > {parent}.{parent_column}")
    open(path, "w").write("\n".join(lines))


def write_mermaid(schema, path):
    lines = ["erDiagram"]
    for child, child_column, parent, parent_column in RELATIONSHIPS:
        if child in schema and parent in schema:
            lines.append(f'  {parent.upper()} ||--o{{ {child.upper()} : "{child_column}"')
    for table, columns in schema.items():
        lines.append(f"  {table.upper()} {{")
        for column_name, column_type in columns:
            marker = " PK" if PRIMARY_KEYS.get(table) == column_name else (
                " FK" if (table, column_name) in {(c, col) for c, col, _, _ in RELATIONSHIPS} else "")
            lines.append(f"    {normalize_type(column_type)[1]} {column_name}{marker}")
        lines.append("  }")
    open(path, "w").write("\n".join(lines))


def write_ddl(schema, path):
    lines = ["-- SFF v2 — DDL del modelo (PK/FK declaradas para herramientas de modelado).",
             "-- Importable en DBeaver, SchemaSpy, pgModeler, MySQL Workbench.",
             "-- Regenerar con: python generate_model.py <ruta_db>", ""]
    for table, columns in schema.items():
        if table in TABLE_NOTES:
            lines.append(f"-- {TABLE_NOTES[table]}")
        column_definitions = []
        for column_name, column_type in columns:
            null_clause = "NOT NULL" if PRIMARY_KEYS.get(table) == column_name else "NULL"
            column_definitions.append(f"    [{column_name}] {normalize_type(column_type)[0]} {null_clause}")
        if PRIMARY_KEYS.get(table):
            column_definitions.append(f"    CONSTRAINT [PK_{table}] PRIMARY KEY ([{PRIMARY_KEYS[table]}])")
        lines.append(f"CREATE TABLE [{table}] (\n" + ",\n".join(column_definitions) + "\n);\n")
    lines.append("-- ─── Relaciones ───")
    for child, child_column, parent, parent_column in RELATIONSHIPS:
        if child in schema and parent in schema and PRIMARY_KEYS.get(parent) == parent_column:
            lines.append(f"ALTER TABLE [{child}] ADD CONSTRAINT [FK_{child}_{parent}] "
                         f"FOREIGN KEY ([{child_column}]) REFERENCES [{parent}] ([{parent_column}]);")
        else:
            lines.append(f"-- lógica (el padre no tiene PK única): {child}.{child_column} → {parent}.{parent_column}")
    open(path, "w").write("\n".join(lines))


if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    schema = read_schema(DB_PATH)
    write_dbml(schema, f"{OUTPUT_DIR}/sff_v2_model.dbml")
    write_mermaid(schema, f"{OUTPUT_DIR}/sff_v2_model.mmd")
    write_ddl(schema, f"{OUTPUT_DIR}/sff_v2_model.sql")
    total_columns = sum(len(columns) for columns in schema.values())
    print(f"modelo emitido: {len(schema)} tablas · {total_columns} columnas · "
          f"{len(RELATIONSHIPS)} relaciones → {OUTPUT_DIR}/")
