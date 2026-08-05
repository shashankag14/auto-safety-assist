from pathlib import Path


# load SQL query from file
def load_sql_query(filename: str, dir: Path = Path(__file__).parent / "queries") -> str:
    filepath = Path(dir) / filename
    return filepath.read_text()