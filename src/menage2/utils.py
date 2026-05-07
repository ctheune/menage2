import json


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

    def undo(
        self, todo_ids: list[int], prev_status: str, texts: list[str], action: str
    ):
        label = texts[0] if len(texts) == 1 else f"{len(texts)} items"
        self(
            "showUndoToast",
            {
                "ids": ",".join(str(i) for i in todo_ids),
                "prevStatus": prev_status,
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
