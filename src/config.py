import os
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
import yaml
from dotenv import load_dotenv

@dataclass(frozen=True)
class SnowflakeConfig:
    account: str
    user: str
    password: str
    role: str
    warehouse: str
    database: str
    schema: str

@dataclass(frozen=True)
class OllamaConfig:
    model: str
    host: str

@dataclass(frozen=True)
class AppConfig:
    snowflake: SnowflakeConfig
    ollama: OllamaConfig
    dataset_config_path: str
    strict_mode: bool = False

def load_app_config(env_path: Optional[str] = None) -> AppConfig:
    """Load application configuration from environment variables and .env file."""
    if env_path:
        load_dotenv(dotenv_path=env_path)
    else:
        load_dotenv()

    snowflake_cfg = SnowflakeConfig(
        account=os.getenv("SNOWFLAKE_ACCOUNT", ""),
        user=os.getenv("SNOWFLAKE_USER", "DATAMIND_APP_USER"),
        password=os.getenv("SNOWFLAKE_PASSWORD", ""),
        role=os.getenv("SNOWFLAKE_ROLE", "DATAMIND_APP_ROLE"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "DATAMIND_WH"),
        database=os.getenv("SNOWFLAKE_DATABASE", "DATAMIND_DB"),
        schema=os.getenv("SNOWFLAKE_SCHEMA", "SALES"),
    )

    ollama_cfg = OllamaConfig(
        model=os.getenv("OLLAMA_MODEL", "gemma3n:e2b"),
        host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
    )

    dataset_path = os.getenv("DATASET_CONFIG", "config/datasets/tpch.yaml")
    strict_mode_env = os.getenv("STRICT_MODE", "false").strip().lower()
    strict_mode = strict_mode_env in ("true", "1", "yes")

    return AppConfig(
        snowflake=snowflake_cfg,
        ollama=ollama_cfg,
        dataset_config_path=dataset_path,
        strict_mode=strict_mode,
    )

def load_dataset_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load and parse the YAML dataset schema allowlist."""
    if config_path is None:
        config_path = os.getenv("DATASET_CONFIG", "config/datasets/tpch.yaml")

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Dataset config not found at path: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return data
