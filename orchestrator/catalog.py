"""Capability catalog shared by the requirement, architecture and implementation agents."""

import re

CAPABILITIES: dict[str, dict] = {
    "shortening": {
        "label": "Short code generation",
        "keywords": ["shortening", "short url", "short code", "short link"],
        "greenfield_keywords": ["url shortener", "shortener"],
        "impact_keywords": ["short", "code"],
        "components": [
            "Short code generator with bounded collision retries",
            "Create/redirect API endpoints",
            "Persistence for URL mappings",
        ],
        "risks": ["Short code collisions under load", "Open redirect / malicious target URLs"],
        "acceptance_criteria": [
            "A valid http/https URL yields a unique short code",
            "Allocation gives up after a bounded number of attempts instead of looping forever",
        ],
    },
    "expiration": {
        "label": "URL expiration",
        "keywords": ["expir"],
        "greenfield_keywords": [],
        "impact_keywords": ["expir"],
        "components": ["Expiry validation and evaluation rules", "Redirect-time expiry check"],
        "risks": [
            "Existing URLs must keep working (backward compatibility)",
            "Clock skew and naive/aware datetime handling",
        ],
        "acceptance_criteria": [
            "Expiry is optional; URLs without expiry never expire",
            "Past or excessively distant expiry values are rejected",
            "Expired URLs stop redirecting",
        ],
    },
    "caching": {
        "label": "Redirect caching",
        "keywords": ["cache", "caching", "latency", "faster", "popular"],
        "greenfield_keywords": [],
        "impact_keywords": ["cache", "redirect"],
        "components": ["Bounded TTL cache for resolved redirects", "Cache invalidation on update"],
        "risks": [
            "Stale redirects after a URL is disabled or updated",
            "Unbounded memory growth without an eviction policy",
        ],
        "acceptance_criteria": [
            "Cache is bounded and entries expire after a TTL",
            "Disabling or updating a URL invalidates its cache entry",
        ],
    },
    "analytics": {
        "label": "Click analytics",
        "keywords": ["analytic", "click", "tracking"],
        "greenfield_keywords": [],
        "impact_keywords": ["click", "analytic"],
        "components": ["Thread-safe click counter", "Analytics read endpoint"],
        "risks": ["Lost updates from concurrent increments", "Analytics growth at scale"],
        "acceptance_criteria": [
            "Concurrent clicks are counted exactly once",
            "Total and last-click timestamp are available per code",
        ],
    },
    "generic": {
        "label": "Generic change",
        "keywords": [],
        "greenfield_keywords": [],
        "impact_keywords": [],
        "components": ["Traceable change record"],
        "risks": ["Requirement could not be mapped to a known capability"],
        "acceptance_criteria": ["Change is traceable to the stated requirement"],
    },
}

_STOPWORDS = {
    "with", "that", "this", "from", "into", "when", "will", "should", "existing", "using",
    "make", "have", "their", "there", "which", "would", "could", "about", "after", "before",
}  # fmt: skip


def detect_capabilities(requirement: str, scenario: str) -> list[str]:
    text = requirement.lower()
    found = []
    for name, spec in CAPABILITIES.items():
        if name == "generic":
            continue
        keywords = list(spec["keywords"])
        if scenario == "greenfield":
            keywords += spec["greenfield_keywords"]
        if any(keyword in text for keyword in keywords):
            found.append(name)
    if not found:
        found = ["shortening"] if scenario == "greenfield" else ["generic"]
    return found


def impact_keywords(capabilities: list[str], requirement: str) -> list[str]:
    keywords: list[str] = []
    for name in capabilities:
        keywords += CAPABILITIES.get(name, {}).get("impact_keywords", [])
    if not keywords:
        words = re.findall(r"[a-z]{6,}", requirement.lower())
        keywords = [w for w in words if w not in _STOPWORDS][:5]
    return sorted(set(keywords))
