import pandas as pd
import json
import os

from pgvector.psycopg2 import register_vector
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from dotenv import load_dotenv
from loguru import logger
from pathlib import Path
from contextlib import closing
from sentence_transformers import SentenceTransformer


# load env variables
load_dotenv()


# load SQL query from file
def load_sql(filename: str, dir: Path = Path(__file__).parent / "sql") -> str:
    filepath = Path(dir) / filename
    return filepath.read_text()


# create database if it doesn't exist
def ensure_database_exists(postgres_user: str | None, postgres_password: str | None, database_name: str = "nhtsa"):
    # connect to postgres
    logger.info("Connecting to postgres...")

    with closing (psycopg2.connect(dbname="postgres", user=postgres_user, password=postgres_password,
                            host="localhost", port="5432")) as conn:
        # need to set this to create a new database in the connection block
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

        with conn.cursor() as cur:
            logger.info("Connected to database successfully!")

            # check if database already exists
            cur.execute(f"SELECT 1 FROM pg_database WHERE datname = '{database_name}'")

            # if not, then create a new one
            if not cur.fetchone():
                cur.execute(f"CREATE DATABASE {database_name}")
                logger.info(f"Database {database_name} created successfully!")
            else:
                logger.info(f"Database {database_name} already exists")


# create tables for recalls and complaints
def create_tables(conn: psycopg2.extensions.connection):
    COMPLAINTS_TABLE_QUERY = load_sql("complaints_table.sql")
    RECALLS_TABLE_QUERY = load_sql("recalls_table.sql")

    try:
        with conn.cursor() as cur:
            cur.execute(COMPLAINTS_TABLE_QUERY)
            cur.execute(RECALLS_TABLE_QUERY)
            conn.commit()
    except Exception as e:
        logger.error(e)
        conn.rollback()


# insert recalls and complaints into database
def insert_recalls(conn: psycopg2.extensions.connection, recalls_df: pd.DataFrame, emb_model: SentenceTransformer):
    RECALLS_INSERT_QUERY = load_sql("recalls_insert.sql")

    try:
        with conn.cursor() as cur:
            for count, (df_idx, row) in enumerate(recalls_df.iterrows()):
                # summary 
                summary_emb = emb_model.encode(row["Summary"]).tolist()
                cur.execute(RECALLS_INSERT_QUERY, (row["NHTSACampaignNumber"], row["Component"], row["vehicle_tag"], row["Summary"], "summary", summary_emb))
        
                # remedy
                remedy_emb = emb_model.encode(row["Remedy"]).tolist()
                cur.execute(RECALLS_INSERT_QUERY, (row["NHTSACampaignNumber"], row["Component"], row["vehicle_tag"], row["Remedy"], "remedy", remedy_emb))

                # consequence
                consequence_emb = emb_model.encode(row["Consequence"]).tolist()
                cur.execute(RECALLS_INSERT_QUERY, (row["NHTSACampaignNumber"], row["Component"], row["vehicle_tag"], row["Consequence"], "consequence", consequence_emb))

                # batch update to database
                if count % 50 == 0:
                    conn.commit()
            
            conn.commit()
            logger.success("Recalls inserted to database successfully!")

    except Exception as e:
        logger.error(e)
        conn.rollback()


def insert_complaints(conn: psycopg2.extensions.connection, complaints_df: pd.DataFrame, emb_model: SentenceTransformer):
    COMPLAINTS_INSERT_QUERY = load_sql("complaints_insert.sql")

    try:
        with conn.cursor() as cur:
            for count, (df_idx, row) in enumerate(complaints_df.iterrows()):
                # complaint
                complaint_emb = emb_model.encode(row["summary"]).tolist()
                cur.execute(COMPLAINTS_INSERT_QUERY, (row["odiNumber"], row["components"], row["crash"], row["fire"], row["vehicle_tag"], row["summary"], complaint_emb))

                # batch update to database
                if count % 50 == 0:
                    conn.commit()
            
            conn.commit()
            logger.success("Complaints inserted to database successfully!")

    except Exception as e:
        logger.error(e)
        conn.rollback()


def main():
    # path to recall and complaints data
    DATA_DIR = Path(__file__).parent.parent / "data"
    recall_json = DATA_DIR / "recalls.json"
    complaints_json = DATA_DIR / "complaints.json"

    # Create dataframes
    recalls_df = pd.DataFrame(json.loads(recall_json.read_text()))
    complaints_df = pd.DataFrame(json.loads(complaints_json.read_text()))

    logger.info(f"Number of recalls: {len(recalls_df)}")
    logger.info(f"Number of complaints: {len(complaints_df)}")

    # load embedding model
    emb_model = SentenceTransformer("all-MiniLM-L6-v2")

    postgres_user = os.environ.get("POSTGRES_USER")
    postgres_password = os.environ.get("POSTGRES_PASSWORD")
    database_name = os.environ.get("DATABASE_NAME") or "nhtsa"

    # create database if it doesn't exist
    ensure_database_exists(postgres_user, postgres_password, database_name)

    # create SQL tables for recalls and complaints if they don't exist
    with closing(psycopg2.connect(dbname=database_name, user=postgres_user, password=postgres_password,
                        host="localhost", port="5432")) as conn:
        # create tables
        create_tables(conn)

        # register vector extension for pgvector in pyschopg2
        register_vector(conn)

        # insert recalls
        insert_recalls(conn, recalls_df, emb_model)

        # insert complaints
        insert_complaints(conn, complaints_df, emb_model)


if __name__ == "__main__":
    main()
