class Seen:
    def __init__(self):
        self.seen = set()

    def __contains__(self, obj):
        result = obj in self.seen
        self.seen.add(obj)
        return result
