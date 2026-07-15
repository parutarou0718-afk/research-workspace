from types import SimpleNamespace

from PySide6.QtWidgets import QLabel

from research_workspace.presentation.pages.overview_page import OverviewPage
from research_workspace.presentation.view_models.overview import OverviewViewModel


def _view_model() -> OverviewViewModel:
    return OverviewViewModel(
        revision_count=17,
        ready_count=8,
        upcoming_conference_count=2,
        upcoming_grant_count=1,
        suggestions=("检查近期截止日期",),
        submission_rows=("论文 | Venue | revision | 2026-07-20Z",),
        activities=("初始化工作台",),
        focus_items=("完成基础设施",),
        focus_progress=33,
    )


def test_overview_renders_view_model_values(qtbot):
    controller = OverviewPage(services=object())
    qtbot.addWidget(controller.widget)

    controller.render(_view_model())

    assert controller.widget.findChild(QLabel, "revisionCountLabel").text() == "17"
    assert controller.ready_count_label.text() == "8"
    assert controller.upcoming_conference_count_label.text() == "2"
    assert controller.upcoming_grant_count_label.text() == "1"
    assert [controller.suggestions_list.item(index).text() for index in range(controller.suggestions_list.count())] == ["检查近期截止日期"]
    assert controller.submission_table.rowCount() == 1
    assert [controller.submission_table.item(0, column).text() for column in range(4)] == ["论文", "Venue", "revision", "2026-07-20Z"]
    assert [controller.activities_list.item(index).text() for index in range(controller.activities_list.count())] == ["初始化工作台"]
    assert [controller.focus_items_list.item(index).text() for index in range(controller.focus_items_list.count())] == ["完成基础设施"]
    assert controller.focus_progress.value() == 33


def test_overview_reads_initial_values_from_injected_query(qtbot):
    view_model = _view_model()

    class Query:
        def execute(self):
            return view_model

    controller = OverviewPage(SimpleNamespace(get_overview=Query()))
    qtbot.addWidget(controller.widget)

    assert controller.revision_count_label.text() == "17"
