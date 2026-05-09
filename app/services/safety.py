"""Safety module for DRM detection and access restrictions."""

import re
from typing import Optional
from urllib.parse import urlparse

from ..constants import DRM_INDICATORS, TEMPORARY_URL_INDICATORS


class SafetyCheck:
    """Result of a safety check."""

    def __init__(
        self,
        is_safe: bool,
        reason: Optional[str] = None,
        drm_detected: bool = False,
        login_required: bool = False,
        payment_required: bool = False,
    ):
        self.is_safe = is_safe
        self.reason = reason
        self.drm_detected = drm_detected
        self.login_required = login_required
        self.payment_required = payment_required


class SafetyService:
    """Safety service for checking content restrictions."""

    def __init__(self):
        self._login_indicators = [
            "login",
            "sign in",
            "sign-in",
            "log in",
            "log-in",
            "signin",
            "login",
            "authenticate",
            "authentication",
        ]

        self._payment_indicators = [
            "subscribe",
            "subscription",
            "premium",
            "paid",
            "purchase",
            "buy",
            "rent",
            "pay per view",
            "ppv",
        ]

        self._captcha_indicators = [
            "captcha",
            "recaptcha",
            "hcaptcha",
            "verify you are human",
            "robot",
            "human verification",
        ]

    def check_html(self, html: str) -> SafetyCheck:
        """Check HTML content for restrictions."""
        html_lower = html.lower()

        # Check for DRM
        drm_result = self._check_drm(html_lower)
        if drm_result:
            return SafetyCheck(
                is_safe=False,
                reason=f"DRM detected: {drm_result}",
                drm_detected=True,
            )

        # Check for login requirement
        if self._check_login_required(html_lower):
            return SafetyCheck(
                is_safe=False,
                reason="Login or authentication may be required",
                login_required=True,
            )

        # Check for payment requirement
        if self._check_payment_required(html_lower):
            return SafetyCheck(
                is_safe=False,
                reason="Payment or subscription may be required",
                payment_required=True,
            )

        # Check for captcha
        if self._check_captcha(html_lower):
            return SafetyCheck(
                is_safe=False,
                reason="Captcha or human verification detected",
            )

        return SafetyCheck(is_safe=True)

    def check_url(self, url: str) -> SafetyCheck:
        """Check URL for restrictions."""
        url_lower = url.lower()

        # Check for DRM in URL
        for indicator in DRM_INDICATORS:
            if indicator.lower() in url_lower:
                return SafetyCheck(
                    is_safe=False,
                    reason=f"DRM indicator in URL: {indicator}",
                    drm_detected=True,
                )

        # Check if URL appears to be temporary
        if self._is_temporary_url(url_lower):
            return SafetyCheck(
                is_safe=True,
                reason="URL appears to be temporary, download quickly",
            )

        return SafetyCheck(is_safe=True)

    def check_response_status(self, status_code: int, url: str) -> SafetyCheck:
        """Check HTTP response status."""
        if status_code == 403:
            return SafetyCheck(
                is_safe=False,
                reason="Access forbidden (403). May need Referer or User-Agent",
            )

        if status_code == 401:
            return SafetyCheck(
                is_safe=False,
                reason="Authentication required (401)",
                login_required=True,
            )

        if status_code == 404:
            return SafetyCheck(
                is_safe=False,
                reason="Resource not found (404). Link may be expired",
            )

        if status_code == 429:
            return SafetyCheck(
                is_safe=False,
                reason="Rate limited (429). Too many requests",
            )

        if status_code >= 500:
            return SafetyCheck(
                is_safe=False,
                reason=f"Server error ({status_code})",
            )

        return SafetyCheck(is_safe=True)

    def _check_drm(self, content: str) -> Optional[str]:
        """Check for DRM indicators."""
        for indicator in DRM_INDICATORS:
            if indicator.lower() in content:
                return indicator
        return None

    def _check_login_required(self, content: str) -> bool:
        """Check if login is required."""
        # Look for login forms or login links
        login_patterns = [
            r'<form[^>]*login[^>]*>',
            r'<input[^>]*type=["\']password["\']',
            r'href=["\'][^"\']*login[^"\']*["\']',
        ]
        for pattern in login_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return True

        # Check for login text in visible content
        for indicator in self._login_indicators:
            if indicator in content:
                return True

        return False

    def _check_payment_required(self, content: str) -> bool:
        """Check if payment is required."""
        for indicator in self._payment_indicators:
            if indicator in content:
                return True
        return False

    def _check_captcha(self, content: str) -> bool:
        """Check for captcha."""
        for indicator in self._captcha_indicators:
            if indicator in content:
                return True
        return False

    def _is_temporary_url(self, url: str) -> bool:
        """Check if URL appears to be temporary."""
        return any(indicator in url for indicator in TEMPORARY_URL_INDICATORS)

    def get_user_friendly_message(self, check: SafetyCheck) -> str:
        """Get user-friendly message for safety check result."""
        if check.is_safe:
            return "Content appears to be safe to download"

        messages = []

        if check.drm_detected:
            messages.append(
                "This content appears to be protected by DRM (Digital Rights Management). "
                "DRM-protected content cannot be legally downloaded without proper authorization."
            )

        if check.login_required:
            messages.append(
                "This content may require login or authentication. "
                "Please log in to the website first, then try again."
            )

        if check.payment_required:
            messages.append(
                "This content may require a paid subscription or purchase. "
                "Please ensure you have proper access before downloading."
            )

        if check.reason and not messages:
            messages.append(check.reason)

        return " ".join(messages) if messages else "Content may have access restrictions"
