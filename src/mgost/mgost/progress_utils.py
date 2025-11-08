from rich.console import RenderableType
from rich.progress import ProgressColumn, Task
from rich.text import Text


class BytesOrIntColumn(ProgressColumn):
    """
        Show human-readable bytes only for
            tasks with task.fields['bytes']==True
            else render empty string int completed/total"""

    @staticmethod
    def _hs(n: int | float) -> str:
        """human_size"""
        n = float(n)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if n < 1024:
                return f"{n:.2f} {unit}"
            n /= 1024
        return f"{n:.2f} PB"

    def render(self, task: Task) -> RenderableType:
        show = task.fields.get("bytes", False)
        completed = task.completed
        total = task.total
        assert isinstance(completed, int)
        assert total is None or isinstance(total, int)
        if not show or task.total is None:
            return Text(f"{completed}/{total}")
        else:
            return Text(
                f"{self._hs(completed)}"
                '/'
                f"{self._hs(total) if total else '?'}"
            )
