import psycopg2
from pgvector.psycopg2 import register_vector

from src.common.config import PostgresConfig


def get_connection(config: PostgresConfig) -> psycopg2.extensions.connection:
    """Connect to the app database and register the pgvector type on the connection."""
    conn = psycopg2.connect(
        dbname=config.database,
        user=config.user,
        password=config.password,
        host=config.host,
        port=config.port,
    )
    register_vector(conn)
    return conn


def get_admin_connection(config: PostgresConfig) -> psycopg2.extensions.connection:
    """Connect to the default 'postgres' database, for bootstrapping the app database itself."""
    return psycopg2.connect(
        dbname="postgres",
        user=config.user,
        password=config.password,
        host=config.host,
        port=config.port,
    )
