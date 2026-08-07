import json
from contextlib import closing
from pathlib import Path

import pandas as pd
import psycopg2
from loguru import logger
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from psycopg2.extras import execute_values
from sentence_transformers import SentenceTransformer

from src.common.config import PostgresConfig, get_postgres_config
from src.common.db import get_admin_connection, get_connection
from src.common.embeddings import get_embedding_model
from src.common.utils import load_sql_query

QUERIES_DIR = Path(__file__).parent / "queries"
DATA_DIR = Path(__file__).parent.parent.parent / "data"


def ensure_database_exists(config: PostgresConfig) -> None:
    """Create the app database if it doesn't exist yet."""
    logger.info("Connecting to postgres...")

    with closing(get_admin_connection(config)) as conn:
        # need to set this to create a new database in the connection block
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

        with conn.cursor() as cur:
            logger.info("Connected to database successfully!")

            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (config.database,))

            if not cur.fetchone():
                cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(config.database)))
                logger.info(f"Database {config.database} created successfully!")
            else:
                logger.info(f"Database {config.database} already exists")


def create_tables(conn: psycopg2.extensions.connection) -> None:
    complaints_table_query = load_sql_query("complaints_table.sql", QUERIES_DIR)
    recalls_table_query = load_sql_query("recalls_table.sql", QUERIES_DIR)

    try:
        with conn.cursor() as cur:
            cur.execute(complaints_table_query)
            cur.execute(recalls_table_query)
        conn.commit()
    except Exception as e:
        logger.error(e)
        conn.rollback()
        raise e


def insert_recalls(conn: psycopg2.extensions.connection, recalls_df: pd.DataFrame, emb_model: SentenceTransformer) -> None:
    recalls_insert_query = load_sql_query("recalls_insert.sql", QUERIES_DIR)

    summaries = recalls_df["Summary"].tolist()
    remedys = recalls_df["Remedy"].tolist()
    consequences = recalls_df["Consequence"].tolist()

    summary_embeddings = emb_model.encode(summaries).tolist()
    remedy_embeddings = emb_model.encode(remedys).tolist()
    consequence_embeddings = emb_model.encode(consequences).tolist()

    recall_records = recalls_df.to_dict("records")

    summary_rows = [(row["NHTSACampaignNumber"], row["Component"], row["vehicle_tag"], row["Summary"], "summary", emb) for row, emb in zip(recall_records, summary_embeddings)]
    remedy_rows = [(row["NHTSACampaignNumber"], row["Component"], row["vehicle_tag"], row["Remedy"], "remedy", emb) for row, emb in zip(recall_records, remedy_embeddings)]
    consequence_rows = [(row["NHTSACampaignNumber"], row["Component"], row["vehicle_tag"], row["Consequence"], "consequence", emb) for row, emb in zip(recall_records, consequence_embeddings)]

    try:
        with conn.cursor() as cur:
            execute_values(cur, recalls_insert_query, summary_rows)
            execute_values(cur, recalls_insert_query, remedy_rows)
            execute_values(cur, recalls_insert_query, consequence_rows)

        conn.commit()
        logger.info("Recalls inserted successfully!")
    except Exception as e:
        logger.error(e)
        conn.rollback()
        raise e


def insert_complaints(conn: psycopg2.extensions.connection, complaints_df: pd.DataFrame, emb_model: SentenceTransformer) -> None:
    complaints_insert_query = load_sql_query("complaints_insert.sql", QUERIES_DIR)

    complaints = complaints_df["summary"].tolist()
    complaints_embeddings = emb_model.encode(complaints).tolist()

    complaints_rows = [
        (row["odiNumber"], row["components"], row["crash"], row["fire"], row["vehicle_tag"], row["summary"], emb)
        for row, emb in zip(complaints_df.to_dict("records"), complaints_embeddings)
    ]

    try:
        with conn.cursor() as cur:
            execute_values(cur, complaints_insert_query, complaints_rows)

        conn.commit()
        logger.info("Complaints inserted successfully!")
    except Exception as e:
        logger.error(e)
        conn.rollback()
        raise e


def build_index() -> None:
    recall_json = DATA_DIR / "recalls.json"
    complaints_json = DATA_DIR / "complaints.json"

    recalls_df = pd.DataFrame(json.loads(recall_json.read_text()))
    complaints_df = pd.DataFrame(json.loads(complaints_json.read_text()))

    logger.info(f"Number of recalls: {len(recalls_df)}")
    logger.info(f"Number of complaints: {len(complaints_df)}")

    emb_model = get_embedding_model()
    config = get_postgres_config()

    ensure_database_exists(config)

    with closing(get_connection(config)) as conn:
        logger.info("Creating tables (if not exists)...")
        create_tables(conn)

        logger.info("Inserting recalls...")
        insert_recalls(conn, recalls_df, emb_model)

        logger.info("Inserting complaints...")
        insert_complaints(conn, complaints_df, emb_model)


if __name__ == "__main__":
    build_index()
