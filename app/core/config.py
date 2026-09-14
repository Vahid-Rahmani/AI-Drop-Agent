"""Environment-backed settings with safe simulation defaults."""

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.finance_config import FinanceConfig
from app.domain import AppMode, PolicyConfig


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "ai-drop-agent"
    app_mode: AppMode = AppMode.SIMULATION
    log_level: str = "INFO"
    database_path: str = "data/ai_drop_agent.db"
    model_provider: str = "mock"
    admin_api_key: str | None = None
    auth_secret: str | None = None
    webhook_secret: str | None = None
    database_url: str = "sqlite:///data/ai_drop_agent.db"
    openai_api_key: str | None = None
    openai_model: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    local_model_base_url: str = "http://localhost:11434/v1"
    local_model_name: str | None = None
    local_model_timeout: float = 30.0
    ebay_environment: str = "sandbox"
    ebay_client_id: str | None = None
    ebay_client_secret: str | None = None
    ebay_refresh_token: str | None = None
    cj_access_token: str | None = None
    cj_api_key: str | None = None
    cj_base_url: str = "https://developers.cjdropshipping.com/api2.0/v1"
    default_vat_rate: float = 0.19
    finance_config_version: str = "simulation-default-2026-09"
    finance_config_verified: bool = False
    marketplace_fee_rate: float = 0.10
    payment_fee_rate: float = 0.02
    advertising_rate: float = 0.05
    expected_return_rate: float = 0.04
    shipping_cost_eur: float = 2.0
    operating_cost_eur: float = 0.50
    discount_rate: float = 0.0
    min_contribution_margin_percent: float = 20.0
    max_daily_spend_eur: float = 100.0
    max_experiment_loss_eur: float = 50.0
    max_product_exposure_eur: float = 250.0
    kill_switch: bool = False

    def production_errors(self) -> list[str]:
        if self.app_mode.value != "live":
            return []
        errors: list[str] = []
        if not self.auth_secret or len(self.auth_secret) < 32:
            errors.append("AUTH_SECRET must contain at least 32 characters")
        if not self.admin_api_key:
            errors.append("ADMIN_API_KEY is required in live mode")
        if not self.webhook_secret or len(self.webhook_secret) < 32:
            errors.append("WEBHOOK_SECRET must contain at least 32 characters")
        if not self.database_url.startswith(("postgresql://", "postgres://")):
            errors.append("DATABASE_URL must point to PostgreSQL in live mode")
        if self.ebay_environment.lower() not in {"sandbox", "production"}:
            errors.append("EBAY_ENV must be sandbox or production")
        try:
            self.finance_config().validate_for_live()
        except ValueError as error:
            errors.append(str(error))
        return errors

    def finance_config(self) -> FinanceConfig:
        return FinanceConfig(
            version=self.finance_config_version,
            verified=self.finance_config_verified,
            currency="EUR",
            vat_rate=self.default_vat_rate,
            marketplace_fee_rate=self.marketplace_fee_rate,
            payment_fee_rate=self.payment_fee_rate,
            advertising_rate=self.advertising_rate,
            expected_return_rate=self.expected_return_rate,
            shipping_cost=self.shipping_cost_eur,
            operating_cost=self.operating_cost_eur,
            discount_rate=self.discount_rate,
        )

    def policy(self) -> PolicyConfig:
        return PolicyConfig(
            min_contribution_margin_percent=self.min_contribution_margin_percent,
            max_daily_spend=self.max_daily_spend_eur,
            max_experiment_loss=self.max_experiment_loss_eur,
            max_product_exposure=self.max_product_exposure_eur,
            kill_switch=self.kill_switch,
        )
