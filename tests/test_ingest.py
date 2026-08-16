from noc_copilot.clauses import Clause
from noc_copilot.ingest import drop_excluded


def ids(clauses):
    return [c.clause_id for c in clauses]


def test_excluded_clause_and_its_descendants_are_dropped():
    clauses = [Clause("6", "A"), Clause("6.3.2", "B"), Clause("5.3.5", "C")]
    assert ids(drop_excluded(clauses, ["6"])) == ["5.3.5"]


def test_exclusion_matches_on_clause_parts_not_string_prefix():
    """'6' must not drop '60.1', and '5.6' must not be dropped by '5'."""
    clauses = [Clause("60.1", "A"), Clause("6.1", "B"), Clause("5.6", "C")]
    assert ids(drop_excluded(clauses, ["6"])) == ["60.1", "5.6"]


def test_letter_exclusion_drops_the_annex_and_its_subclauses():
    clauses = [Clause("A", "Change history"), Clause("A.1", "x"), Clause("B.1", "y")]
    assert ids(drop_excluded(clauses, ["A"])) == ["B.1"]


def test_no_exclusions_keeps_everything():
    clauses = [Clause("6.3.2", "A"), Clause("5.3.5", "B")]
    assert ids(drop_excluded(clauses, [])) == ["6.3.2", "5.3.5"]
