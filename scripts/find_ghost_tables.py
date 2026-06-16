"""
List PostgreSQL tables that exist in the DB but are not declared on SQLAlchemy Base,
and print suggested ORM model class definitions.
"""
import os
import re
from typing import List, Set, Tuple

from dotenv import load_dotenv
from sqlalchemy import MetaData, create_engine
from sqlalchemy import types as sa_types
from sqlalchemy.schema import ForeignKeyConstraint, UniqueConstraint

load_dotenv()

from database import Base  # noqa: E402


def _orm_table_keys() -> Set[Tuple[str, str]]:
    """(schema, name) for each table registered on Base."""
    return {(t.schema or "public", t.name) for t in Base.metadata.tables.values()}


def _python_class_name(table_name: str) -> str:
    parts = [p for p in table_name.split("_") if p]
    return "".join(p.title() for p in parts) or "GhostTable"


def _sanitize_attr(name: str) -> str:
    if not name.isidentifier():
        return f"x_{re.sub(r'[^0-9a-zA-Z_]', '_', name)}"
    if name in {"metadata", "registry"}:
        return f"{name}_"
    return name


def _format_column_type(col) -> str:
    t = col.type
    if isinstance(t, sa_types.String):
        if t.length:
            return f"String({t.length})"
        return "String()"
    if isinstance(t, sa_types.Text):
        return "Text()"
    if isinstance(t, sa_types.Integer):
        return "Integer()"
    if isinstance(t, sa_types.BigInteger):
        return "BigInteger()"
    if isinstance(t, sa_types.SmallInteger):
        return "SmallInteger()"
    if isinstance(t, sa_types.Boolean):
        return "Boolean()"
    if isinstance(t, sa_types.DateTime):
        return "DateTime()"
    if isinstance(t, sa_types.Date):
        return "Date()"
    if isinstance(t, sa_types.Time):
        return "Time()"
    if isinstance(t, sa_types.Float):
        return "Float()"
    if isinstance(t, sa_types.Numeric):
        p, s = t.precision, t.scale
        if p is not None and s is not None:
            return f"Numeric({p}, {s})"
        if p is not None:
            return f"Numeric({p})"
        return "Numeric()"
    if isinstance(t, sa_types.LargeBinary):
        return "LargeBinary()"
    if isinstance(t, sa_types.JSON):
        return "JSON()"
    return type(t).__name__


def _imports_for_type_string(type_str: str) -> Set[str]:
    names: Set[str] = set()
    for name in (
        "String",
        "Text",
        "Integer",
        "BigInteger",
        "SmallInteger",
        "Boolean",
        "DateTime",
        "Date",
        "Time",
        "Float",
        "Numeric",
        "LargeBinary",
        "JSON",
    ):
        if name in type_str:
            names.add(name)
    return names


def _table_level_constraints(table) -> List[str]:
    """UniqueConstraint / ForeignKeyConstraint for __table_args__ (PKs come from Column flags)."""
    lines: List[str] = []
    for cons in table.constraints:
        if isinstance(cons, UniqueConstraint):
            cols = ", ".join(repr(c.name) for c in cons.columns)
            name = f", name={cons.name!r}" if cons.name else ""
            lines.append(f"UniqueConstraint({cols}{name})")
        elif isinstance(cons, ForeignKeyConstraint):
            local_cols = [c.name for c in cons.columns]
            remote_cols = [f"{fk.column.table.fullname}.{fk.column.name}" for fk in cons.elements]
            loc = ", ".join(repr(c) for c in local_cols)
            rem = ", ".join(repr(c) for c in remote_cols)
            name = f", name={cons.name!r}" if cons.name else ""
            ondel = f", ondelete={cons.ondelete!r}" if getattr(cons, "ondelete", None) else ""
            onupd = f", onupdate={cons.onupdate!r}" if getattr(cons, "onupdate", None) else ""
            lines.append(f"ForeignKeyConstraint([{loc}], [{rem}]{name}{ondel}{onupd})")
    return lines


def _server_default_fragment(col, engine) -> Tuple[str, bool]:
    """
    Returns (python_fragment, needs_text_import).
    Uses dialect compilation when possible.
    """
    if col.server_default is None:
        return "", False
    arg = getattr(col.server_default, "arg", None)
    if arg is None:
        return f"server_default={col.server_default!r}", False
    try:
        sql = str(arg.compile(dialect=engine.dialect))
        return f"server_default=text({sql!r})", True
    except Exception:
        return f"server_default=text({str(arg)!r})", True


def print_model_for_ghost_table(table, engine) -> None:
    class_name = _python_class_name(table.name)
    tablename = table.name
    schema = table.schema or "public"

    col_lines: List[str] = []
    all_type_names: Set[str] = set()
    needs_text = False

    for col in table.columns:
        attr = _sanitize_attr(col.name)
        type_str = _format_column_type(col)
        all_type_names.update(_imports_for_type_string(type_str))

        parts: List[str] = [type_str]
        if col.primary_key:
            parts.append("primary_key=True")
        if col.autoincrement is True:
            parts.append("autoincrement=True")
        if not col.nullable and not col.primary_key:
            parts.append("nullable=False")
        if col.unique and not col.primary_key:
            parts.append("unique=True")

        sd, sd_text = _server_default_fragment(col, engine)
        if sd:
            parts.append(sd)
            needs_text = needs_text or sd_text

        if col.default is not None and col.server_default is None:
            parts.append(f"default={col.default!r}")

        fk = list(col.foreign_keys)
        if fk:
            fk0 = fk[0]
            target = f"{fk0.column.table.fullname}.{fk0.column.name}"
            parts.append(f"ForeignKey({target!r})")
            all_type_names.add("ForeignKey")

        col_lines.append(f"    {attr} = Column({', '.join(parts)})")

    constraint_items = _table_level_constraints(table)
    for c in constraint_items:
        if "UniqueConstraint" in c:
            all_type_names.add("UniqueConstraint")
        if "ForeignKeyConstraint" in c:
            all_type_names.add("ForeignKeyConstraint")

    if needs_text:
        all_type_names.add("text")

    print()
    print("# " + "=" * 72)
    print(f"# Ghost table: {table.fullname}")
    print("# " + "=" * 72)
    print()

    import_names = sorted(all_type_names - {"text"})
    if "text" in all_type_names:
        import_names.append("text")
    imports_line = ", ".join(import_names)
    print(
        f"# Suggested imports (merge with database.py): "
        f"Column, {imports_line}"
    )
    print()

    print(f"class {class_name}(Base):")

    table_args_parts: List[str] = []
    if schema != "public":
        table_args_parts.append(f'{{"schema": "{schema}"}}')
    table_args_parts.extend(constraint_items)

    if len(table_args_parts) == 1 and table_args_parts[0].startswith("{"):
        print(f"    __tablename__ = '{tablename}'")
        print(f"    __table_args__ = {table_args_parts[0]}")
    elif table_args_parts:
        print(f"    __tablename__ = '{tablename}'")
        print("    __table_args__ = (")
        for p in table_args_parts:
            print(f"        {p},")
        print("    )")
    else:
        print(f"    __tablename__ = '{tablename}'")

    for line in col_lines:
        print(line)

    print()


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is not set in the environment or .env file.")
        return
    if database_url.startswith("sqlite"):
        print("This script targets PostgreSQL (DATABASE_URL is SQLite).")
        return

    engine = create_engine(database_url)
    orm_keys = _orm_table_keys()

    reflected = MetaData()
    reflected.reflect(bind=engine)

    skip_schemas = {"information_schema", "pg_catalog", "pg_toast"}

    ghosts = []
    for _key, tbl in reflected.tables.items():
        sch = tbl.schema or "public"
        if sch in skip_schemas:
            continue
        if (sch, tbl.name) not in orm_keys:
            ghosts.append(tbl)

    ghosts.sort(key=lambda t: (t.schema or "", t.name))

    if not ghosts:
        print("No ghost tables found (every reflected user table is registered on Base).")
        return

    print(f"Found {len(ghosts)} ghost table(s) (in DB but not in Base.metadata):\n")
    for t in ghosts:
        print(f"  - {t.fullname}")

    print("\n" + "=" * 72)
    print("Suggested SQLAlchemy models (copy into database.py and adjust as needed)")
    print("=" * 72)

    for tbl in ghosts:
        print_model_for_ghost_table(tbl, engine)


if __name__ == "__main__":
    main()
