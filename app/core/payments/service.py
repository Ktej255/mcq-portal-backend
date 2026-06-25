"""
Cashfree Payment Service.

Wraps the official cashfree_pg SDK (v6.x) to provide:
- Order creation (PGCreateOrder)
- Webhook signature verification (HMAC-SHA256)
- Refund initiation (PGOrderCreateRefund)
- Order status fetching (PGFetchOrder)

All methods handle SDK exceptions gracefully with logging.
The Cashfree secret key is NEVER exposed in errors or log messages.

Requirements: 1.1, 1.4, 3.1, 7.1, 8.3, 8.4, 8.5
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from dataclasses import dataclass
from typing import Optional

from app.core.payments.config import CashfreeConfig

logger = logging.getLogger(__name__)


@dataclass
class CreateOrderResult:
    """Successful order creation response from Cashfree."""

    cashfree_order_id: str
    payment_session_id: str


@dataclass
class RefundResult:
    """Successful refund initiation response from Cashfree."""

    cashfree_refund_id: str
    refund_status: str


@dataclass
class OrderStatusResult:
    """Fetched order status from Cashfree."""

    cashfree_order_id: str
    order_status: str
    payment_method: Optional[str] = None
    cashfree_payment_id: Optional[str] = None


class CashfreeServiceError(Exception):
    """Raised when a Cashfree API call fails.

    Contains a sanitized user-facing message (never exposes the secret key).
    """

    def __init__(self, message: str, code: str = "CASHFREE_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class CashfreePaymentService:
    """Service layer wrapping the Cashfree PG Python SDK (v6.x).

    Instantiated once at application startup with validated CashfreeConfig.
    All Cashfree API calls go through this service.
    """

    def __init__(self, config: CashfreeConfig) -> None:
        from cashfree_pg.api_client import Cashfree

        self._config = config
        self._secret_key = config.secret_key

        environment = (
            Cashfree.SANDBOX
            if config.environment == "sandbox"
            else Cashfree.PRODUCTION
        )

        self._client = Cashfree(
            XEnvironment=environment,
            XClientId=config.app_id,
            XClientSecret=config.secret_key,
        )

        logger.info(
            "CashfreePaymentService initialized (environment=%s)",
            config.environment,
        )

    # ------------------------------------------------------------------
    # Order Creation
    # ------------------------------------------------------------------

    def create_order(
        self,
        order_id: str,
        amount: int,
        customer_id: str,
        customer_email: str,
        customer_phone: str,
        return_url: str,
    ) -> CreateOrderResult:
        """Create a Cashfree payment order via PGCreateOrder.

        Args:
            order_id: Unique order reference (e.g. "SARIT-xxxxxxxxxxxx").
            amount: Order amount in whole INR.
            customer_id: Firebase/Supabase user ID.
            customer_email: Student email address.
            customer_phone: Student phone number.
            return_url: URL to redirect the student after payment.

        Returns:
            CreateOrderResult with cashfree_order_id and payment_session_id.

        Raises:
            CashfreeServiceError: If the Cashfree API call fails.
        """
        from cashfree_pg.models.create_order_request import CreateOrderRequest
        from cashfree_pg.models.customer_details import CustomerDetails
        from cashfree_pg.models.order_meta import OrderMeta

        try:
            customer = CustomerDetails(
                customer_id=customer_id,
                customer_phone=customer_phone,
                customer_email=customer_email,
            )
            order_meta = OrderMeta(return_url=return_url)
            request = CreateOrderRequest(
                order_id=order_id,
                order_amount=float(amount),
                order_currency="INR",
                customer_details=customer,
                order_meta=order_meta,
            )

            response = self._client.PGCreateOrder(request, None, None)
            data = response.data

            cashfree_order_id = getattr(data, "cf_order_id", None) or getattr(
                data, "order_id", order_id
            )
            payment_session_id = getattr(data, "payment_session_id", None)

            if not payment_session_id:
                logger.error(
                    "Cashfree PGCreateOrder returned no payment_session_id "
                    "for order_id=%s",
                    order_id,
                )
                raise CashfreeServiceError(
                    message="Payment session could not be created. Please try again.",
                    code="ORDER_SESSION_MISSING",
                )

            logger.info(
                "Cashfree order created: order_id=%s, cf_order_id=%s",
                order_id,
                cashfree_order_id,
            )

            return CreateOrderResult(
                cashfree_order_id=str(cashfree_order_id),
                payment_session_id=str(payment_session_id),
            )

        except CashfreeServiceError:
            raise
        except Exception as exc:
            # Sanitize: never include secret key in logs
            error_msg = str(exc)
            if self._secret_key and self._secret_key in error_msg:
                error_msg = error_msg.replace(self._secret_key, "***REDACTED***")

            logger.error(
                "Cashfree PGCreateOrder failed for order_id=%s: %s",
                order_id,
                error_msg,
            )
            raise CashfreeServiceError(
                message="Failed to create payment order. Please try again later.",
                code="ORDER_CREATION_FAILED",
            ) from None

    # ------------------------------------------------------------------
    # Webhook Signature Verification
    # ------------------------------------------------------------------

    def verify_webhook_signature(
        self, timestamp: str, raw_body: str, signature: str
    ) -> bool:
        """Verify Cashfree webhook signature using HMAC-SHA256.

        The expected signature is computed as:
            message = timestamp + rawBody
            HMAC-SHA256(secret_key, message) → base64 encoded

        Args:
            timestamp: The x-webhook-timestamp header value.
            raw_body: The raw request body as a string.
            signature: The x-webhook-signature header value.

        Returns:
            True if the signature is valid, False otherwise.
        """
        try:
            message = timestamp + raw_body
            computed = hmac.new(
                key=self._secret_key.encode("utf-8"),
                msg=message.encode("utf-8"),
                digestmod=hashlib.sha256,
            ).digest()
            computed_b64 = base64.b64encode(computed).decode("utf-8")

            return hmac.compare_digest(computed_b64, signature)

        except Exception as exc:
            # Sanitize error — never expose secret key
            error_msg = str(exc)
            if self._secret_key and self._secret_key in error_msg:
                error_msg = error_msg.replace(self._secret_key, "***REDACTED***")

            logger.error(
                "Webhook signature verification error: %s", error_msg
            )
            return False

    # ------------------------------------------------------------------
    # Refund Initiation
    # ------------------------------------------------------------------

    def initiate_refund(
        self,
        cashfree_order_id: str,
        refund_amount: float,
        refund_id: str,
    ) -> RefundResult:
        """Initiate a refund via Cashfree PGOrderCreateRefund.

        Args:
            cashfree_order_id: The Cashfree order identifier to refund.
            refund_amount: Amount to refund in INR (supports partial refunds).
            refund_id: Unique refund reference generated by our system.

        Returns:
            RefundResult with the Cashfree refund ID and status.

        Raises:
            CashfreeServiceError: If the Cashfree refund API call fails.
        """
        from cashfree_pg.models.create_order_refund_request import (
            CreateOrderRefundRequest,
        )

        try:
            request = CreateOrderRefundRequest(
                refund_amount=float(refund_amount),
                refund_id=refund_id,
                refund_note=f"Refund for order {cashfree_order_id}",
            )

            response = self._client.PGOrderCreateRefund(
                cashfree_order_id, request, None, None
            )
            data = response.data

            cf_refund_id = getattr(data, "cf_refund_id", None) or getattr(
                data, "refund_id", refund_id
            )
            refund_status = getattr(data, "refund_status", "PENDING")

            logger.info(
                "Cashfree refund initiated: order=%s, refund_id=%s, "
                "cf_refund_id=%s, status=%s",
                cashfree_order_id,
                refund_id,
                cf_refund_id,
                refund_status,
            )

            return RefundResult(
                cashfree_refund_id=str(cf_refund_id),
                refund_status=str(refund_status),
            )

        except CashfreeServiceError:
            raise
        except Exception as exc:
            error_msg = str(exc)
            if self._secret_key and self._secret_key in error_msg:
                error_msg = error_msg.replace(self._secret_key, "***REDACTED***")

            logger.error(
                "Cashfree PGOrderCreateRefund failed for order=%s, "
                "refund_id=%s: %s",
                cashfree_order_id,
                refund_id,
                error_msg,
            )
            raise CashfreeServiceError(
                message="Failed to initiate refund. Please try again later.",
                code="REFUND_INITIATION_FAILED",
            ) from None

    # ------------------------------------------------------------------
    # Fetch Order Status
    # ------------------------------------------------------------------

    def fetch_order_status(
        self, cashfree_order_id: str
    ) -> OrderStatusResult:
        """Fetch current order status from Cashfree via PGFetchOrder.

        Args:
            cashfree_order_id: The Cashfree order identifier.

        Returns:
            OrderStatusResult with the current order status and payment details.

        Raises:
            CashfreeServiceError: If the Cashfree API call fails.
        """
        try:
            response = self._client.PGFetchOrder(
                cashfree_order_id, None, None
            )
            data = response.data

            order_status = getattr(data, "order_status", "UNKNOWN")
            payment_method = getattr(data, "payment_method", None)
            cf_payment_id = getattr(data, "cf_payment_id", None)

            logger.info(
                "Cashfree order status fetched: order=%s, status=%s",
                cashfree_order_id,
                order_status,
            )

            return OrderStatusResult(
                cashfree_order_id=cashfree_order_id,
                order_status=str(order_status),
                payment_method=str(payment_method) if payment_method else None,
                cashfree_payment_id=str(cf_payment_id) if cf_payment_id else None,
            )

        except CashfreeServiceError:
            raise
        except Exception as exc:
            error_msg = str(exc)
            if self._secret_key and self._secret_key in error_msg:
                error_msg = error_msg.replace(self._secret_key, "***REDACTED***")

            logger.error(
                "Cashfree PGFetchOrder failed for order=%s: %s",
                cashfree_order_id,
                error_msg,
            )
            raise CashfreeServiceError(
                message="Failed to fetch order status. Please try again later.",
                code="ORDER_FETCH_FAILED",
            ) from None
