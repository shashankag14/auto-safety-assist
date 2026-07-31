import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import numpy as np
import pandas as pd
import json
import os

from dotenv import load_dotenv
from loguru import logger
from pathlib import Path
from sentence_transformers import SentenceTransformer

# load env variables
load_dotenv()

SQL_DIR = Path(__file__).parent / "sql"

# path to recall and complaints data
DATA_DIR = Path('data')
recall_json = DATA_DIR / "recalls.json"
complaints_json = DATA_DIR / "complaints.json"

# Create dataframes
recalls_df = pd.DataFrame(json.loads(recall_json.read_text()))
complaints_df = pd.DataFrame(json.loads(complaints_json.read_text()))

logger.info(f"Number of recalls: {len(recalls_df)}")
logger.info(f"Number of complaints: {len(complaints_df)}")

emb_model = SentenceTransformer("all-MiniLM-L6-v2")

# emb_model.encode(text)

postgres_user = os.environ.get("POSTGRES_USER")
postgres_password = os.environ.get("POSTGRES_PASSWORD")
database_name = "nhtsa"


def create_database(postgres_user, postgres_password):
    # connect to postgres
    conn = psycopg2.connect(dbname="postgres",
                            user=postgres_user,
                            password=postgres_password,
                            host="localhost",
                            port="5432")

    # to create a new database in the connection block
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

    cur = conn.cursor()

    # check if database already exists
    cur.execute("SELECT 1 FROM pg_database WHERE datname = 'nhtsa'")

    # if not, then create a new one
    if not cur.fetchone():
        cur.execute("CREATE DATABASE nhtsa")
        logger.info("Database nhtsa created successfully!")
    else:
        logger.info("Database nhtsa already exists")

    cur.close()
    conn.close()


def load_sql(filename: str, dir: Path = SQL_DIR) -> str:
    filepath = Path(dir) / filename
    return filepath.read_text()

create_database(postgres_user, postgres_password)


conn = psycopg2.connect(dbname=database_name,
                        user=postgres_user,
                        password=postgres_password,
                        host="localhost",
                        port="5432")

cur = conn.cursor()

COMPLAINTS_TABLE_QUERY = load_sql("complaints_table.sql")
try:
    cur.execute(COMPLAINTS_TABLE_QUERY)    
    conn.commit()
except Exception as e:
    logger.error(e)
    conn.rollback()


RECALLS_TABLE_QUERY = load_sql("recalls_table.sql")
try:
    cur.execute(RECALLS_TABLE_QUERY)    
    conn.commit()
except Exception as e:
    logger.error(e)
    conn.rollback()

RECALLS_INSERT_QUERY = load_sql("recalls_insert.sql")
COMPLAINTS_INSERT_QUERY = load_sql("complaints_insert.sql")

# update recalls to database
try:
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


try:
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


cur.close()
conn.close()


