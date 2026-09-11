"""
Command & Control (C2) External Webhook Forwarder.
Registers external webhook endpoints and asynchronously forwards all new IBVAP alerts
to integrated C2 and situational awareness systems.
"""

import uuid
import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)


class C2WebhookDispatcher:
    """
    Manages external C2 webhook endpoints and dispatches alert payloads.
    """

    def __init__(self):
        self.webhooks: Dict[str, Dict[str, Any]] = {}

    def register_webhook(self, webhook_url: str, description: str = "C2 System", secret_token: Optional[str] = None) -> Dict[str, Any]:
        """Register a new external C2 webhook URL."""
        webhook_id = str(uuid.uuid4())
        record = {
            "id": webhook_id,
            "webhook_url": webhook_url,
            "description": description,
            "secret_token": secret_token,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "active": True
        }
        self.webhooks[webhook_id] = record
        logger.info(f"Registered C2 Webhook [{webhook_id[:8]}]: {webhook_url} ({description})")
        return record

    def list_webhooks(self) -> List[Dict[str, Any]]:
        """List all active C2 webhooks."""
        return list(self.webhooks.values())

    def delete_webhook(self, webhook_id: str) -> bool:
        """Remove a webhook endpoint."""
        if webhook_id in self.webhooks:
            del self.webhooks[webhook_id]
            logger.info(f"Removed C2 Webhook [{webhook_id[:8]}]")
            return True
        return False

    async def dispatch_alert(self, alert_data: Dict[str, Any]):
        """
        Asynchronously forward an alert payload to all registered C2 endpoints.
        Non-blocking with short timeout.
        """
        active_hooks = [h for h in self.webhooks.values() if h.get("active", True)]
        if not active_hooks:
            return

        async with httpx.AsyncClient(timeout=3.0) as client:
            tasks = []
            for hook in active_hooks:
                url = hook["webhook_url"]
                headers = {"Content-Type": "application/json"}
                if hook.get("secret_token"):
                    headers["Authorization"] = f"Bearer {hook['secret_token']}"

                payload = {
                    "source": "IBVAP_BORDER_ANALYTICS",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "alert": alert_data
                }
                tasks.append(self._send_single_webhook(client, url, headers, payload, hook["id"]))

            await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_single_webhook(self, client: httpx.AsyncClient, url: str, headers: dict, payload: dict, hook_id: str):
        """Send HTTP POST payload to a single webhook endpoint."""
        try:
            resp = await client.post(url, json=payload, headers=headers)
            logger.info(f"C2 Webhook [{hook_id[:8]}] forwarded to {url} -> Status: {resp.status_code}")
        except Exception as e:
            logger.warning(f"Failed to forward alert to C2 Webhook [{hook_id[:8]}] at {url}: {e}")
