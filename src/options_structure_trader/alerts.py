from __future__ import annotations

import os

import httpx

from .config import Settings
from .models import PaperTrade, SetupEvent


def format_production_alert(setup: SetupEvent, trade: PaperTrade) -> str:
    plan = setup.trade_plan
    icon = "🟢" if setup.side.value == "LONG" else "🔴"
    why = "\n".join(f"- {reason}" for reason in setup.reason)
    return (f"{icon} OPTIONS_STRUCTURE PAPER {setup.side.value} - {setup.ticker}\n"
            f"Setup: {setup.setup_type.value}\nScore: {setup.score.total:.0f}/100\n"
            f"Score model: {setup.score.score_model_version}\nMode: Production Paper\n\n"
            f"Entry: {plan.entry_zone_low:.2f}-{plan.entry_zone_high:.2f}\nStop: {plan.stop_initial:.2f}\n"
            f"TP1: {plan.targets[0]:.2f}\nTP2: {plan.targets[1]:.2f}\nTP3: {plan.targets[2]:.2f}\n"
            f"Risk: ${plan.risk_dollars:.2f}\n\nWhy:\n{why}\n\nInvalidation:\n{plan.invalidation_logic}\n\n"
            "No real order placed. Paper mode only.")


class AlertDispatcher:
    def __init__(self, settings: Settings):
        self.settings = settings

    def send(self, message: str) -> dict[str, str]:
        if self.settings.get("alerts.console_enabled", True):
            print(message)
        if self.settings.get("alerts.telegram_enabled", False):
            token, chat_id = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
            if not token or not chat_id:
                return {"status": "skipped", "reason": "Telegram credentials missing"}
            response = httpx.post(f"https://api.telegram.org/bot{token}/sendMessage",
                                  json={"chat_id": chat_id, "text": message}, timeout=10)
            response.raise_for_status()
            return {"status": "sent"}
        return {"status": "console_only"}

