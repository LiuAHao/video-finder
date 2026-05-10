"""Tests for safety module."""

import pytest
from app.services.safety import SafetyService, SafetyCheck


class TestSafetyCheckHTML:
    """Test SafetyService.check_html()."""

    def setup_method(self):
        self.service = SafetyService()

    def test_safe_html(self):
        html = "<html><body><video src='https://cdn.example.com/v.mp4'></video></body></html>"
        result = self.service.check_html(html)
        assert result.is_safe is True
        assert result.drm_detected is False
        assert result.login_required is False
        assert result.payment_required is False

    def test_drm_widevine(self):
        html = "<html><body><script>widevine</script></body></html>"
        result = self.service.check_html(html)
        assert result.is_safe is False
        assert result.drm_detected is True
        assert "widevine" in result.reason.lower()

    def test_drm_content_protection(self):
        html = "<html><body><ContentProtection schemeIdUri='urn:uuid:edef8ba9'></ContentProtection></body></html>"
        result = self.service.check_html(html)
        assert result.is_safe is False
        assert result.drm_detected is True

    def test_login_form_detected(self):
        html = "<html><body><form action='/login'><input type='password'></form></body></html>"
        result = self.service.check_html(html)
        assert result.is_safe is False
        assert result.login_required is True

    def test_login_link_detected(self):
        html = '<html><body><a href="/login">Sign In</a></body></html>'
        result = self.service.check_html(html)
        assert result.is_safe is False
        assert result.login_required is True

    def test_payment_subscription(self):
        html = "<html><body><div>Subscribe to watch this video</div></body></html>"
        result = self.service.check_html(html)
        assert result.is_safe is False
        assert result.payment_required is True

    def test_payment_premium(self):
        html = "<html><body><div>Premium content only</div></body></html>"
        result = self.service.check_html(html)
        assert result.is_safe is False
        assert result.payment_required is True

    def test_captcha_detected(self):
        html = "<html><body><div class='g-recaptcha'></div></body></html>"
        result = self.service.check_html(html)
        assert result.is_safe is False
        assert "captcha" in result.reason.lower() or "verification" in result.reason.lower()

    def test_drm_takes_priority_over_login(self):
        html = "<html><body><script>widevine</script><form action='/login'></form></body></html>"
        result = self.service.check_html(html)
        assert result.is_safe is False
        assert result.drm_detected is True


class TestSafetyCheckURL:
    """Test SafetyService.check_url()."""

    def setup_method(self):
        self.service = SafetyService()

    def test_safe_url(self):
        result = self.service.check_url("https://cdn.example.com/video.m3u8")
        assert result.is_safe is True

    def test_drm_in_url(self):
        result = self.service.check_url("https://cdn.example.com/widevine/stream.mpd")
        assert result.is_safe is False
        assert result.drm_detected is True

    def test_temporary_url(self):
        result = self.service.check_url("https://cdn.example.com/video.m3u8?token=abc123")
        assert result.is_safe is True
        assert "temporary" in result.reason.lower()

    def test_temporary_url_with_expires(self):
        result = self.service.check_url("https://cdn.example.com/video.m3u8?expires=1234567890")
        assert result.is_safe is True


class TestSafetyCheckResponseStatus:
    """Test SafetyService.check_response_status()."""

    def setup_method(self):
        self.service = SafetyService()

    def test_200_ok(self):
        result = self.service.check_response_status(200, "https://example.com")
        assert result.is_safe is True

    def test_403_forbidden(self):
        result = self.service.check_response_status(403, "https://example.com")
        assert result.is_safe is False
        assert "403" in result.reason

    def test_401_unauthorized(self):
        result = self.service.check_response_status(401, "https://example.com")
        assert result.is_safe is False
        assert result.login_required is True

    def test_404_not_found(self):
        result = self.service.check_response_status(404, "https://example.com")
        assert result.is_safe is False
        assert "404" in result.reason

    def test_429_rate_limited(self):
        result = self.service.check_response_status(429, "https://example.com")
        assert result.is_safe is False
        assert "429" in result.reason

    def test_500_server_error(self):
        result = self.service.check_response_status(500, "https://example.com")
        assert result.is_safe is False
        assert "500" in result.reason

    def test_503_server_error(self):
        result = self.service.check_response_status(503, "https://example.com")
        assert result.is_safe is False


class TestSafetyGetUserFriendlyMessage:
    """Test SafetyService.get_user_friendly_message()."""

    def setup_method(self):
        self.service = SafetyService()

    def test_safe_message(self):
        check = SafetyCheck(is_safe=True)
        msg = self.service.get_user_friendly_message(check)
        assert "safe" in msg.lower()

    def test_drm_message(self):
        check = SafetyCheck(is_safe=False, drm_detected=True, reason="DRM detected")
        msg = self.service.get_user_friendly_message(check)
        assert "drm" in msg.lower()

    def test_login_message(self):
        check = SafetyCheck(is_safe=False, login_required=True, reason="Login required")
        msg = self.service.get_user_friendly_message(check)
        assert "login" in msg.lower() or "log in" in msg.lower()

    def test_payment_message(self):
        check = SafetyCheck(is_safe=False, payment_required=True, reason="Payment required")
        msg = self.service.get_user_friendly_message(check)
        assert "subscription" in msg.lower() or "paid" in msg.lower() or "purchase" in msg.lower()

    def test_generic_unsafe_message(self):
        check = SafetyCheck(is_safe=False, reason="Rate limited")
        msg = self.service.get_user_friendly_message(check)
        assert "rate limited" in msg.lower()
