import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from menage2.schemas import UndoEntry


class Seen:
    def __init__(self):
        self.seen = set()

    def __contains__(self, obj):
        result = obj in self.seen
        self.seen.add(obj)
        return result


class HXTrigger:
    def __init__(self, response):
        self.response = response
        self.data = {}

    def __bool__(self):
        return bool(self.data)

    def undo(self, entries: list["UndoEntry"], texts: list[str], action: str):
        """Offer to put `entries` back the way they were.

        Each entry is a snapshot taken before the change — id, status and due
        date — so one mechanism covers completing, holding, postponing and
        reactivating, and a batch spanning several previous states undoes
        correctly item by item.

        The snapshot travels as a JSON string: it ends up in a hidden form
        field, so it has to be a string by the time the client sees it.
        """
        label = texts[0] if len(texts) == 1 else f"{len(texts)} items"
        self(
            "showUndoToast",
            {
                "entries": json.dumps([e.model_dump(mode="json") for e in entries]),
                "label": label,
                "action": action,
            },
        )

    def __call__(self, key, value=None):
        assert key not in self.data
        self.data[key] = value
        self.response.headers["HX-Trigger"] = str(self)

    def __str__(self):
        return json.dumps(self.data)
