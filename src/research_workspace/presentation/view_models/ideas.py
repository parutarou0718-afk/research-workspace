"""Qt-free Idea presentation coordination."""

from research_workspace.presentation.view_models.papers import CrudListViewModel


class IdeasViewModel(CrudListViewModel):
    def delete(self, row):
        return self._call("delete_idea", row)

    def restore(self, row):
        return self._call("restore_idea", row)
