from pathlib import Path


def load_sql_query(filename: str, dir: Path) -> str:
    """Load a SQL query from a service/job's own queries directory."""
    filepath = Path(dir) / filename
    try:
        return filepath.read_text()
    except FileNotFoundError as e:
        raise FileNotFoundError(f"SQL query not found at path: {filepath}") from e
