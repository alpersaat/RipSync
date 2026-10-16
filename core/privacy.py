"""
RipSync Privacy & Sensitive Data Protection Module
Provides algorithms to detect passwords, credit card numbers, personal identity numbers,
cryptographic keys, and tokens to prevent unauthorized clipboard monitoring or logging.
"""

import re
import urllib.parse
from typing import Optional


def is_luhn_valid(candidate: str) -> bool:
    """Validates a number string using the Luhn algorithm."""
    digits = [int(c) for c in candidate if c.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    
    checksum = 0
    reverse_digits = digits[::-1]
    for idx, d in enumerate(reverse_digits):
        if idx % 2 == 1:
            d = d * 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def contains_credit_card(text: str) -> bool:
    """Detects credit/debit card numbers (Visa, Mastercard, Amex, Discover, Troy, etc.)."""
    # Looks for sequences of digits possibly separated by spaces or dashes
    potential_matches = re.findall(r'(?:\d[ -]*?){13,19}', text)
    for match in potential_matches:
        cleaned = re.sub(r'[\s-]', '', match)
        if cleaned.isdigit() and 13 <= len(cleaned) <= 19:
            # Check common issuer prefixes
            # Visa (4), Mastercard (51-55, 22-27), Amex (34, 37), Discover (6011, 65), Troy (9792)
            if is_luhn_valid(cleaned):
                return True
    return False


def is_valid_tc_kimlik(candidate: str) -> bool:
    """Validates Republic of Turkey ID number (T.C. Kimlik No)."""
    if not candidate.isdigit() or len(candidate) != 11:
        return False
    if candidate[0] == '0':
        return False
    
    digits = [int(d) for d in candidate]
    odd_sum = sum(digits[0:9:2])
    even_sum = sum(digits[1:8:2])
    
    tenth = ((odd_sum * 7) - even_sum) % 10
    if tenth != digits[9]:
        return False
    
    eleventh = sum(digits[:10]) % 10
    if eleventh != digits[10]:
        return False
    
    return True


def contains_identity_number(text: str) -> bool:
    """Detects SSN or Turkish ID numbers."""
    # US SSN (123-45-6789)
    if re.search(r'\b\d{3}-\d{2}-\d{4}\b', text):
        return True
    
    # 11-digit potential Turkish IDs
    for match in re.findall(r'\b\d{11}\b', text):
        if is_valid_tc_kimlik(match):
            return True
            
    return False


# Common private key headers
PRIVATE_KEY_PATTERNS = [
    re.compile(r'-----BEGIN\s+(?:[A-Z0-9_-]+\s+)?PRIVATE\s+KEY-----', re.IGNORECASE),
    re.compile(r'-----BEGIN\s+RSA\s+PRIVATE\s+KEY-----', re.IGNORECASE),
    re.compile(r'-----BEGIN\s+OPENSSH\s+PRIVATE\s+KEY-----', re.IGNORECASE),
    re.compile(r'-----BEGIN\s+PGP\s+PRIVATE\s+KEY\s+BLOCK-----', re.IGNORECASE),
    re.compile(r'-----BEGIN\s+ENCRYPTED\s+PRIVATE\s+KEY-----', re.IGNORECASE),
]

# API key & token patterns
TOKEN_PATTERNS = [
    # JWT tokens (three base64 segments)
    re.compile(r'\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b'),
    # Bearer tokens
    re.compile(r'\bBearer\s+[A-Za-z0-9_\-\.]{16,}\b', re.IGNORECASE),
    # GitHub Tokens
    re.compile(r'\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b'),
    re.compile(r'\bgithub_pat_[A-Za-z0-9_]{36,}\b'),
    # AWS Access Key ID
    re.compile(r'\b(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}\b'),
    # Google API Key
    re.compile(r'\bAIza[0-9A-Za-z\-_]{35}\b'),
    # OpenAI API Key
    re.compile(r'\bsk-[A-Za-z0-9]{20,}\b'),
    # Slack tokens
    re.compile(r'\bxox[baprs]-[0-9]{10,13}-[0-9]{10,13}-[a-zA-Z0-9]{24,32}\b'),
    # Generic API Key / Secret assignments
    re.compile(
        r'(?i)\b(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret)\b\s*[:=]\s*["\']?[a-zA-Z0-9_\-]{12,}["\']?'
    )
]

# Labeled password patterns (Password managers, copy-paste credentials)
PASSWORD_FIELD_PATTERNS = [
    re.compile(r'(?i)\b(?:password|parola|şifre|passwd|pwd)\s*[:=]\s*\S+'),
    re.compile(r'(?i)\b(?:pin|cvv|cvc|cvv2|security\s*code)\s*[:=]\s*\d{3,6}\b'),
    re.compile(r'(?i)\b(?:kullanıcı\s*adı|username|user|email|eposta)\b.*(?:\b(?:password|parola|şifre|pwd)\b)', re.DOTALL),
]

# Sensitive query parameters in URLs
SENSITIVE_URL_QUERY_PARAMS = {
    "password", "pwd", "passwd", "pass", "secret", "client_secret",
    "auth_token", "access_token", "api_key", "apikey", "pin", "cvv"
}


def is_complex_password(text: str) -> bool:
    """
    Detects if a plain non-URL single-line string looks like a generated password.
    Typically: 8 to 64 chars, no whitespace, contains mix of lowercase, uppercase, digits, symbols.
    """
    s = text.strip()
    if len(s) < 8 or len(s) > 128:
        return False
    if " " in s or "\t" in s or "\n" in s or "\r" in s:
        return False
    # If it is a normal URL, it's checked by URL rules instead
    if s.startswith("http://") or s.startswith("https://"):
        return False

    has_upper = bool(re.search(r'[A-Z]', s))
    has_lower = bool(re.search(r'[a-z]', s))
    has_digit = bool(re.search(r'[0-9]', s))
    has_symbol = bool(re.search(r'[^A-Za-z0-9]', s))

    # If it contains 3 or 4 of these character classes, it is likely a generated password
    classes_matched = sum([has_upper, has_lower, has_digit, has_symbol])
    return classes_matched >= 3


def contains_sensitive_url_data(url: str) -> bool:
    """Checks if a URL carries sensitive credentials in userinfo or query params."""
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return False

    # Check HTTP Basic auth in URL: http://user:pass@host
    if parsed.password:
        return True

    # Check sensitive query parameters
    if parsed.query:
        try:
            params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
            for param_key in params.keys():
                k_clean = param_key.lower().strip()
                if k_clean in SENSITIVE_URL_QUERY_PARAMS:
                    return True
        except Exception:
            pass

    return False


def is_sensitive_text(text: Optional[str]) -> bool:
    """
    Master check: returns True if text contains sensitive information
    (passwords, credit cards, identity numbers, API keys, private keys, etc.).
    """
    if not text:
        return False

    clean = text.strip()
    if not clean:
        return False

    # 1. Credit Card Check
    if contains_credit_card(clean):
        return True

    # 2. Identity Number Check (TC Kimlik / SSN)
    if contains_identity_number(clean):
        return True

    # 3. Private Cryptographic Keys
    for pattern in PRIVATE_KEY_PATTERNS:
        if pattern.search(clean):
            return True

    # 4. API Keys & Authentication Tokens
    for pattern in TOKEN_PATTERNS:
        if pattern.search(clean):
            return True

    # 5. Labeled Password / Secret Patterns
    for pattern in PASSWORD_FIELD_PATTERNS:
        if pattern.search(clean):
            return True

    # 6. Sensitive URL inspection
    if clean.startswith("http://") or clean.startswith("https://"):
        if contains_sensitive_url_data(clean):
            return True
    else:
        # 7. Non-URL High Entropy / Password Check
        if is_complex_password(clean):
            return True

    return False
