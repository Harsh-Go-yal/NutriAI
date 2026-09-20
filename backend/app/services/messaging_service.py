"""
Text messaging out of the app, with a provider chosen by what is configured.

Ranked by how fast you can actually get one working:

  Telegram   ~5 min   BotFather -> token. No approval, no fees, no DLT.
  WhatsApp   ~15 min  Twilio *sandbox* only (join code, testing numbers).
                      Production WhatsApp needs Meta Business verification,
                      which takes days, not minutes.
  SMS        days     Indian SMS needs TRAI DLT registration of the sender ID
                      and every template. Do not plan a demo around it.

Nothing here raises if a provider is missing; `status()` reports what is
configured so the UI can say so honestly instead of failing at send time.
"""
import logging
from typing import Any, Dict, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"
TWILIO_API = "https://api.twilio.com/2010-04-01"


class MessagingService:
    # -- capability reporting ---------------------------------------------

    def configured_channels(self) -> Dict[str, bool]:
        return {
            "telegram": bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID),
            "whatsapp": bool(settings.TWILIO_ACCOUNT_SID
                             and settings.TWILIO_AUTH_TOKEN
                             and settings.TWILIO_WHATSAPP_FROM),
            "sms": bool(settings.TWILIO_ACCOUNT_SID
                        and settings.TWILIO_AUTH_TOKEN
                        and settings.TWILIO_SMS_FROM),
        }

    def status(self) -> Dict[str, Any]:
        channels = self.configured_channels()
        return {
            "channels": channels,
            "default": self.default_channel(),
            "setup": {
                "telegram": "Message @BotFather -> /newbot -> put the token in "
                            "TELEGRAM_BOT_TOKEN, then send your bot a message "
                            "and read the chat id from getUpdates. ~5 minutes.",
                "whatsapp": "Twilio sandbox: console -> Messaging -> Try WhatsApp, "
                            "join with the code from your phone, then set "
                            "TWILIO_* vars. Sandbox only -- production needs "
                            "Meta Business verification (days).",
                "sms": "Indian SMS requires TRAI DLT registration of sender ID "
                       "and templates. Not a same-day option.",
            },
            "recommendation": (
                "Use Telegram for the demo. It is the only one of the three "
                "that genuinely works in minutes with no external approval."
            ),
        }

    def default_channel(self) -> Optional[str]:
        channels = self.configured_channels()
        for name in ("telegram", "whatsapp", "sms"):
            if channels[name]:
                return name
        return None

    # -- sending -----------------------------------------------------------

    async def send(self, text: str, phone: Optional[str] = None,
                   channel: Optional[str] = None) -> Dict[str, Any]:
        channel = (channel or self.default_channel() or "").lower()

        if not channel:
            return {
                "sent": False,
                "reason": "No messaging channel is configured.",
                "help": self.status()["setup"],
            }

        if channel == "telegram":
            return await self._telegram(text)
        if channel in {"whatsapp", "sms"}:
            return await self._twilio(text, phone, channel)
        return {"sent": False, "reason": f"Unknown channel '{channel}'."}

    async def _telegram(self, text: str) -> Dict[str, Any]:
        token, chat_id = settings.TELEGRAM_BOT_TOKEN, settings.TELEGRAM_CHAT_ID
        if not (token and chat_id):
            return {"sent": False, "channel": "telegram",
                    "reason": "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set."}
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(
                    f"{TELEGRAM_API}/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": text},
                    timeout=15.0,
                )
            ok = res.status_code == 200
            return {"sent": ok, "channel": "telegram",
                    "status_code": res.status_code,
                    "detail": None if ok else res.text[:300]}
        except Exception as e:
            logger.warning(f"Telegram send failed: {e}")
            return {"sent": False, "channel": "telegram", "reason": str(e)}

    async def _twilio(self, text: str, phone: Optional[str],
                      channel: str) -> Dict[str, Any]:
        sid, token = settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN
        sender = (settings.TWILIO_WHATSAPP_FROM if channel == "whatsapp"
                  else settings.TWILIO_SMS_FROM)

        if not (sid and token and sender):
            return {"sent": False, "channel": channel,
                    "reason": f"Twilio credentials for {channel} are not set."}
        if not phone:
            return {"sent": False, "channel": channel,
                    "reason": "No destination phone number on file."}

        to = f"whatsapp:{phone}" if channel == "whatsapp" else phone
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(
                    f"{TWILIO_API}/Accounts/{sid}/Messages.json",
                    data={"From": sender, "To": to, "Body": text},
                    auth=(sid, token),
                    timeout=20.0,
                )
            ok = res.status_code in (200, 201)
            return {"sent": ok, "channel": channel, "status_code": res.status_code,
                    "detail": None if ok else res.text[:300]}
        except Exception as e:
            logger.warning(f"Twilio {channel} send failed: {e}")
            return {"sent": False, "channel": channel, "reason": str(e)}


messaging_service = MessagingService()
