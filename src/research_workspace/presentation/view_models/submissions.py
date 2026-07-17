"""Qt-free Submission presentation coordination."""

from research_workspace.presentation.view_models.papers import CrudListViewModel


class SubmissionsViewModel(CrudListViewModel):
    def delete(self, row):
        return self._call("delete_submission", row)

    def restore(self, row):
        return self._call("restore_submission", row)
