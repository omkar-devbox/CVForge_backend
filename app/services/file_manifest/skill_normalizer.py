"""Skill normalization and deduplication using RapidFuzz."""

import re
from typing import Dict, List, Set
from rapidfuzz import fuzz, process


class SkillNormalizer:
    """Normalizes candidate skill lists, eliminates duplicate variations, and maps aliases."""

    # Canonical skill mappings for known variations
    CANONICAL_SKILLS_MAP: Dict[str, str] = {
        
    }

    SIMILARITY_THRESHOLD = 88.0

    @classmethod
    def normalize_single_skill(cls, skill: str) -> str:
        """Standardizes a single skill string using canonical dictionary lookup."""
        clean = skill.strip()
        if not clean:
            return ""

        lookup_key = re.sub(r"[\s\-_]+", " ", clean).strip().lower()
        if lookup_key in cls.CANONICAL_SKILLS_MAP:
            return cls.CANONICAL_SKILLS_MAP[lookup_key]

        # Preserve standard capitalization if title/upper, else title case
        if clean.isupper() and len(clean) <= 5:
            return clean
        if any(c.isupper() for c in clean[1:]):
            return clean  # Preserve mixed camelCase like JavaScript, AutoCAD
        return clean.title()

    @classmethod
    def normalize_and_deduplicate(cls, skills: List[str]) -> List[str]:
        """Normalizes and deduplicates a list of skills using RapidFuzz token matching."""
        if not skills:
            return []

        normalized_candidates: List[str] = []
        seen_exact: Set[str] = set()

        # Step 1: Canonical lookup and basic cleanup
        for raw in skills:
            if not raw or not isinstance(raw, str):
                continue
            cleaned = cls.normalize_single_skill(raw)
            if not cleaned or len(cleaned) < 2:
                continue

            lowered = cleaned.lower()
            if lowered not in seen_exact:
                seen_exact.add(lowered)
                normalized_candidates.append(cleaned)

        # Step 2: Fuzzy cluster deduplication with RapidFuzz
        final_skills: List[str] = []
        for candidate in normalized_candidates:
            matched = False
            for existing in final_skills:
                # Compare token sort ratio
                ratio = fuzz.token_sort_ratio(candidate.lower(), existing.lower())
                if ratio >= cls.SIMILARITY_THRESHOLD:
                    matched = True
                    break

            if not matched:
                final_skills.append(candidate)

        return final_skills
