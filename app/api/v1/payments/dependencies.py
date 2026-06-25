"""
Payment endpoint dependencies.

Provides the CashfreePaymentService instance from app state.
Returns HTTP 503 if the payment service is not configured.
"""

from fastapi import HTTPException, Request, status


def get_payment_service(request: Request):
    """Retrieve the CashfreePaymentService from app state.

    Raises HTTP 503 if the service was not initialized at startup
    (credentials missing or initialization failure).
    """
    service = getattr(request.app.state, "payment_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment service is currently unavailable. Please try again later.",
        )
    return service
