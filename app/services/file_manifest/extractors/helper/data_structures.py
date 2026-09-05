# ----------------------------------------
# Imports
# ----------------------------------------

from typing import Any, Dict, List, Optional


# ----------------------------------------
# Case Insensitive List
# ----------------------------------------

class CaseInsensitiveList(list):

    def __contains__(self, item: Any) -> bool:
        if super().__contains__(item):
            return True

        if isinstance(item, str):
            lower_item = item.lower()
            return any(
                isinstance(element, str) and element.lower() == lower_item
                for element in self
            )

        return False


# ----------------------------------------
# Entity Extraction Result
# ----------------------------------------

class EntityExtractionResult(dict):

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.__dict__ = self

    # ----------------------------------------
    # Property Accessors
    # ----------------------------------------

    @property
    def candidate_name(self) -> Optional[str]:
        return self.get("name")

    @property
    def candidate_role(self) -> Optional[str]:
        return self.get("role")

    @property
    def role(self) -> Optional[str]:
        return self.get("role")

    @property
    def emails(self) -> List[str]:
        return self.get("email", [])

    @property
    def phones(self) -> List[str]:
        return self.get("contact_no", [])

    @property
    def linkedin(self) -> Optional[str]:
        links = self.get("links")
        return getattr(links, "linkedin", None) if links else None

    @property
    def github(self) -> Optional[str]:
        links = self.get("links")
        return getattr(links, "github", None) if links else None

    @property
    def sections(self) -> Dict[str, str]:
        return self.get("_sections", {})


# ----------------------------------------
# Public Exports
# ----------------------------------------

__all__ = [
    "CaseInsensitiveList",
    "EntityExtractionResult",
]
