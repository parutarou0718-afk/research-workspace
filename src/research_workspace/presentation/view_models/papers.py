"""Qt-free Paper presentation coordination."""

from __future__ import annotations


class CrudListViewModel:
    def __init__(self, query, actions) -> None:
        self._query = query
        self._actions = actions
        self.rows = ()

    def refresh(self):
        self.rows = (
            self._query.project(include_deleted=True)
            if self._query is not None else ()
        )
        return self.rows

    def _call(self, action, row):
        return getattr(self._actions, action)(row.id)


class PapersViewModel(CrudListViewModel):
    def delete(self, row):
        return self._call("delete_paper", row)

    def restore(self, row):
        return self._call("restore_paper", row)
