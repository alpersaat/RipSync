import os
import pytest
from core.database import Database
from core.site_rules import SiteRulesManager
from core.categories import get_categorized_save_dir

def test_site_rules_manager_add_remove():
    db = Database(":memory:")
    mgr = SiteRulesManager(db)

    # Initial rules list should be empty
    assert mgr.get_rules() == []

    # Add rules
    assert mgr.add_rule("github.com", "C:\\Downloads\\Github") is True
    assert mgr.add_rule("https://artstation.com/artwork", "D:\\Art", enabled=True) is True

    rules = mgr.get_rules()
    assert len(rules) == 2
    domains = [r["domain"] for r in rules]
    assert "github.com" in domains
    assert "artstation.com" in domains

    # Matching exact domain
    assert mgr.match_rule("https://github.com/torvalds/linux/archive/master.zip") == os.path.normpath("C:\\Downloads\\Github")

    # Matching subdomain
    assert mgr.match_rule("https://raw.github.com/user/repo/file.txt") == os.path.normpath("C:\\Downloads\\Github")

    # Matching artstation
    assert mgr.match_rule("https://artstation.com/image.jpg") == os.path.normpath("D:\\Art")

    # Non-matching domain
    assert mgr.match_rule("https://google.com/test.zip") is None

    # Remove rule
    assert mgr.remove_rule("github.com") is True
    assert mgr.match_rule("https://github.com/file.zip") is None
    assert len(mgr.get_rules()) == 1

def test_categories_integration_with_site_rules():
    db = Database(":memory:")
    mgr = SiteRulesManager(db)
    mgr.add_rule("github.com", "C:\\CustomGithubFolder")

    # Extension would normally categorise .zip to 'Arşivler'
    # But site rule must take precedence
    target_dir = get_categorized_save_dir(
        filename="archive.zip",
        base_dir="C:\\Downloads",
        url="https://github.com/alpersaat/RipSync/archive/main.zip",
        site_rules=mgr
    )
    assert os.path.normpath(target_dir) == os.path.normpath("C:\\CustomGithubFolder")

    # Unmatched url falls back to standard category
    fallback_dir = get_categorized_save_dir(
        filename="archive.zip",
        base_dir="C:\\Downloads",
        url="https://other.com/file.zip",
        site_rules=mgr
    )
    assert "Arşivler" in fallback_dir

