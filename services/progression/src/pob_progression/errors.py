class ProgressionError(RuntimeError):
    """A stage copy could not be stored without changing the source build."""


class CraftingError(RuntimeError):
    """The imported modifier data cannot support this craft."""
