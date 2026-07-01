"""集中式設定,從環境變數 / .env 載入。

所有可調參數都集中於此,讓 agent、Web 伺服器與 Docker image 讀取同一個來源。
機密資料(API key)只從環境變數讀取,本模組絕不會將其寫入磁碟。

LLM 供應商不寫死:以 LLM_PROVIDER 在 anthropic / openai 之間切換,
各自讀取對應的 API key 與(選填的)模型名稱。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# 若本地存在 .env 則載入(在以環境變數注入設定的正式環境中為無作用)。
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
RUNS_DIR = BASE_DIR / "app" / "runs"

# 各供應商在未指定 AGENT_MODEL 時採用的預設模型。
_DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-4o",
}


def _as_bool(value: str | None, default: bool) -> bool:
    """將環境變數字串解析為布林值。"""
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str | None, default: int) -> int:
    """將環境變數字串解析為整數,失敗時回傳預設值。"""
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """從環境解析而來、不可變動的執行期設定。"""

    llm_provider: str
    anthropic_api_key: str
    openai_api_key: str
    agent_model: str
    agent_max_steps: int
    headless: bool
    port: int
    daily_run_limit: int
    runs_dir: Path

    @property
    def active_api_key(self) -> str:
        """回傳目前所選供應商對應的 API key。"""
        if self.llm_provider == "openai":
            return self.openai_api_key
        return self.anthropic_api_key

    @property
    def has_api_key(self) -> bool:
        """目前所選供應商是否已設定 API key。"""
        return bool(self.active_api_key)


def get_settings() -> Settings:
    """依目前環境變數建立一個 Settings 實例。

    Zeabur(以及多數 PaaS)會在執行期注入 ``$PORT``,此處會予以採用。
    """
    provider = os.environ.get("LLM_PROVIDER", "anthropic").strip().lower()
    if provider not in _DEFAULT_MODELS:
        provider = "anthropic"

    # 模型:優先使用 AGENT_MODEL,否則採用該供應商的預設模型。
    model = os.environ.get("AGENT_MODEL", "").strip() or _DEFAULT_MODELS[provider]

    return Settings(
        llm_provider=provider,
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        agent_model=model,
        agent_max_steps=_as_int(os.environ.get("AGENT_MAX_STEPS"), 25),
        headless=_as_bool(os.environ.get("HEADLESS"), True),
        port=_as_int(os.environ.get("PORT"), 8000),
        daily_run_limit=_as_int(os.environ.get("DAILY_RUN_LIMIT"), 50),
        runs_dir=RUNS_DIR,
    )
