import abc
import uuid
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel


class PaymentChargeResult(BaseModel):
    success: bool
    provider: str
    provider_ref: str
    amount: Decimal
    currency: str
    card_brand: Optional[str] = None
    card_last4: Optional[str] = None
    error_message: Optional[str] = None


class PaymentRefundResult(BaseModel):
    success: bool
    refund_ref: str
    error_message: Optional[str] = None


class BasePaymentGateway(abc.ABC):
    @abc.abstractmethod
    async def charge(
        self,
        amount: Decimal,
        currency: str,
        token: str,
        description: Optional[str] = None,
    ) -> PaymentChargeResult:
        """Process a credit/debit card charge using a token."""
        pass

    @abc.abstractmethod
    async def refund(
        self,
        provider_ref: str,
        amount: Decimal,
        reason: Optional[str] = None,
    ) -> PaymentRefundResult:
        """Process a refund for a previous transaction."""
        pass


class MockPaymentGateway(BasePaymentGateway):
    """
    Mock payment gateway simulating Stripe/Braintree for development and tests.
    Recognizes test tokens such as 'tok_visa', 'tok_mastercard', 'tok_fail'.
    """

    async def charge(
        self,
        amount: Decimal,
        currency: str,
        token: str,
        description: Optional[str] = None,
    ) -> PaymentChargeResult:
        if token == "tok_fail":
            return PaymentChargeResult(
                success=False,
                provider="stripe_mock",
                provider_ref="",
                amount=amount,
                currency=currency,
                error_message="Card was declined by issuing bank (insufficient funds)",
            )

        # Infer mock brand from token name if provided
        brand = "Visa"
        last4 = "4242"
        if "mastercard" in token.lower():
            brand = "Mastercard"
            last4 = "5555"
        elif "amex" in token.lower():
            brand = "American Express"
            last4 = "0005"

        return PaymentChargeResult(
            success=True,
            provider="stripe_mock",
            provider_ref=f"ch_mock_{uuid.uuid4().hex[:16]}",
            amount=amount,
            currency=currency.upper(),
            card_brand=brand,
            card_last4=last4,
        )

    async def refund(
        self,
        provider_ref: str,
        amount: Decimal,
        reason: Optional[str] = None,
    ) -> PaymentRefundResult:
        return PaymentRefundResult(
            success=True,
            refund_ref=f"re_mock_{uuid.uuid4().hex[:16]}",
        )


# Default singleton instance
payment_gateway: BasePaymentGateway = MockPaymentGateway()
