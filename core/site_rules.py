import os
import json
from urllib.parse import urlparse
from typing import List, Dict, Optional, Any
from core.database import Database

class SiteRulesManager:
    """
    Manages custom download directories for specific websites or domains.
    Example:
      github.com -> C:/Users/alper/Downloads/Github
      artstation.com -> C:/Users/alper/Downloads/Artstation
    """
    SETTING_KEY = "site_rules_json"

    def __init__(self, db: Database):
        self.db = db

    def get_rules(self) -> List[Dict[str, Any]]:
        """Returns the list of configured site rules."""
        raw = self.db.get_setting(self.SETTING_KEY, "[]")
        try:
            rules = json.loads(raw)
            if isinstance(rules, list):
                return rules
        except Exception as e:
            try:
                from core.logger import get_logger
                get_logger("site_rules").debug(f"Site kuralları JSON ayrıştırma hatası: {e}")
            except Exception:
                pass
        return []

    def save_rules(self, rules: List[Dict[str, Any]]):
        """Saves the list of site rules."""
        self.db.set_setting(self.SETTING_KEY, json.dumps(rules))

    def add_rule(self, domain: str, folder: str, enabled: bool = True) -> bool:
        """Adds or updates a domain rule."""
        clean_domain = domain.strip().lower()
        if not clean_domain or not folder:
            return False

        # Normalize domain (strip protocol if accidentally pasted)
        if "://" in clean_domain:
            try:
                parsed = urlparse(clean_domain)
                clean_domain = parsed.netloc or clean_domain
            except Exception as e:
                try:
                    from core.logger import get_logger
                    get_logger("site_rules").debug(f"Alan adı ayrıştırma hatası ({clean_domain}): {e}")
                except Exception:
                    pass
        clean_domain = clean_domain.split("/")[0].split(":")[0]

        rules = self.get_rules()
        # Remove existing rule with same domain
        rules = [r for r in rules if r.get("domain", "").lower() != clean_domain]
        rules.append({
            "domain": clean_domain,
            "folder": os.path.normpath(folder),
            "enabled": enabled
        })
        self.save_rules(rules)
        return True

    def remove_rule(self, domain: str) -> bool:
        """Removes a domain rule."""
        clean_domain = domain.strip().lower()
        rules = self.get_rules()
        new_rules = [r for r in rules if r.get("domain", "").lower() != clean_domain]
        if len(new_rules) != len(rules):
            self.save_rules(new_rules)
            return True
        return False

    def match_rule(self, url: str) -> Optional[str]:
        """
        Given a URL or domain string, finds the first matching enabled rule and returns its target folder.
        Matches exact domain, subdomains (e.g. raw.github.com matches github.com), or wildcard patterns.
        """
        if not url:
            return None

        clean_url = url.strip()
        netloc = ""
        if "://" in clean_url:
            try:
                netloc = urlparse(clean_url).netloc.lower()
            except Exception:
                netloc = clean_url.lower()
        else:
            netloc = clean_url.split("/")[0].lower()

        netloc = netloc.split(":")[0]  # strip port
        if not netloc:
            return None

        rules = self.get_rules()
        for rule in rules:
            if not rule.get("enabled", True):
                continue
            r_domain = rule.get("domain", "").strip().lower()
            if not r_domain:
                continue

            # Check exact match
            if netloc == r_domain:
                return rule.get("folder")

            # Check subdomain match (e.g., assets.example.com ends with .example.com)
            if netloc.endswith(f".{r_domain}"):
                return rule.get("folder")

        return None

