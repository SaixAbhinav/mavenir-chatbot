from noc_copilot.clauses import parse_leaf_clauses


def test_leaf_clauses_only(make_docx):
    path = make_docx("s.docx", [
        ("Heading 1", "5\tConnection control"),
        ("Heading 2", "5.3\tRRC procedures"),
        ("Heading 3", "5.3.5\tRRC reconnection"),
        ("Heading 4", "5.3.5.1\tGeneral"),
        ("Normal", "This clause describes the general case."),
        ("Heading 4", "5.3.5.2\tInitiation"),
        ("Normal", "The UE shall initiate the procedure."),
    ])
    clauses = parse_leaf_clauses(path)
    assert [c.clause_id for c in clauses] == ["5.3.5.1", "5.3.5.2"]


def test_parent_with_body_and_children_yields_both(make_docx):
    path = make_docx("s.docx", [
        ("Heading 3", "5.3.5\tRRC reconnection"),
        ("Normal", "Preamble text belonging to 5.3.5 itself."),
        ("Heading 4", "5.3.5.1\tGeneral"),
        ("Normal", "Child body."),
    ])
    clauses = parse_leaf_clauses(path)
    assert [c.clause_id for c in clauses] == ["5.3.5", "5.3.5.1"]
    assert clauses[0].body == "Preamble text belonging to 5.3.5 itself."


def test_empty_container_clause_is_dropped(make_docx):
    path = make_docx("s.docx", [
        ("Heading 3", "5.3.5\tRRC reconnection"),
        ("Heading 4", "5.3.5.1\tGeneral"),
        ("Normal", "Child body."),
    ])
    assert [c.clause_id for c in parse_leaf_clauses(path)] == ["5.3.5.1"]


def test_ancestors_are_recorded_in_order(make_docx):
    path = make_docx("s.docx", [
        ("Heading 1", "5\tConnection control"),
        ("Heading 2", "5.3\tRRC procedures"),
        ("Heading 3", "5.3.5\tRRC reconnection"),
        ("Normal", "Body."),
    ])
    clause = parse_leaf_clauses(path)[0]
    assert clause.ancestors == [("5", "Connection control"), ("5.3", "RRC procedures")]
    assert clause.title == "RRC reconnection"


def test_unnumbered_headings_are_ignored(make_docx):
    path = make_docx("s.docx", [
        ("Heading 1", "Foreword"),
        ("Normal", "Not a numbered clause."),
        ("Heading 1", "5\tConnection control"),
        ("Normal", "Real body."),
    ])
    assert [c.clause_id for c in parse_leaf_clauses(path)] == ["5"]


def test_headings_split_on_spaces_as_well_as_tabs(make_docx):
    path = make_docx("s.docx", [
        ("Heading 2", "5.3.5   RRC reconnection"),
        ("Normal", "Body."),
    ])
    clause = parse_leaf_clauses(path)[0]
    assert clause.clause_id == "5.3.5"
    assert clause.title == "RRC reconnection"


def test_annex_leaf_clause_is_parsed(make_docx):
    path = make_docx("s.docx", [
        ("Heading 2", "A.1\tIntroduction"),
        ("Normal", "Annex body text."),
    ])
    clause = parse_leaf_clauses(path)[0]
    assert clause.clause_id == "A.1"
    assert clause.title == "Introduction"
    assert clause.body == "Annex body text."


def test_nested_annex_clause_records_annex_ancestors_in_order(make_docx):
    path = make_docx("s.docx", [
        ("Heading 1", "Annex A (normative):\tGeneral"),
        ("Heading 2", "A.3\tPDU specification"),
        ("Heading 3", "A.3.1\tGeneral principles"),
        ("Heading 4", "A.3.1.1\tASN.1 clauses"),
        ("Normal", "Body."),
    ])
    clause = parse_leaf_clauses(path)[0]
    assert clause.clause_id == "A.3.1.1"
    assert clause.ancestors == [
        ("A", "General"),
        ("A.3", "PDU specification"),
        ("A.3.1", "General principles"),
    ]


def test_letter_suffixed_clause_ids_are_parsed(make_docx):
    """3GPP inserts a clause between two existing ones by suffixing a letter:
    TS 38.321 v17.15.0 has 19 of them, including the 2-step random access
    procedure. Before this, their bodies folded into the preceding clause."""
    path = make_docx("s.docx", [
        ("Heading 2", "5.1.1\tRandom Access procedure initialization"),
        ("Normal", "Base body."),
        ("Heading 2", "5.1.1a\tInitialization of variables"),
        ("Normal", "Suffixed body."),
        ("Heading 3", "5.1.1a.1\tSub-clause"),
        ("Normal", "Nested body."),
        ("Heading 2", "5.7b\tDRX for MBS Multicast"),
        ("Normal", "Another body."),
    ])
    clauses = parse_leaf_clauses(path)
    assert [c.clause_id for c in clauses] == ["5.1.1", "5.1.1a", "5.1.1a.1", "5.7b"]
    assert clauses[1].body == "Suffixed body."
    assert clauses[2].ancestors == [("5.1.1a", "Initialization of variables")]


def test_annex_banner_is_a_clause_so_its_body_is_attributed_to_it(make_docx):
    """An annex banner carries a real clause id — the letter. Folding it into
    whichever clause happened to be open attributed the annex's prose, and the
    Change history table at the end of every 3GPP document, to an unrelated
    clause."""
    path = make_docx("s.docx", [
        ("Heading 1", "9\tLast numbered clause"),
        ("Normal", "Body of clause 9."),
        ("Heading 1", "Annex C (informative):\tI-RNTI Reference Profiles"),
        ("Normal", "Prose belonging to Annex C itself."),
    ])
    clauses = parse_leaf_clauses(path)
    assert [c.clause_id for c in clauses] == ["9", "C"]
    assert clauses[0].body == "Body of clause 9."
    assert clauses[1].title == "I-RNTI Reference Profiles"
    assert clauses[1].body == "Prose belonging to Annex C itself."


def test_annex_banner_title_may_be_on_a_second_line(make_docx):
    """Real banners carry a line break: 'Annex G (informative):\\nChange history'."""
    path = make_docx("s.docx", [
        ("Heading 1", "9\tLast numbered clause"),
        ("Normal", "Body of clause 9."),
        ("Heading 8", "Annex G (informative):\nChange history"),
        ("Normal", "Revision table would go here."),
    ])
    clauses = parse_leaf_clauses(path)
    assert [(c.clause_id, c.title) for c in clauses] == [
        ("9", "Last numbered clause"),
        ("G", "Change history"),
    ]


def test_annex_word_alone_does_not_start_a_clause(make_docx):
    """'Annexes' or prose beginning with the word must not match the banner."""
    path = make_docx("s.docx", [
        ("Heading 1", "5\tConnection control"),
        ("Normal", "Real body."),
        ("Heading 2", "Annexes referenced by this clause"),
        ("Normal", "Still clause 5."),
    ])
    clauses = parse_leaf_clauses(path)
    assert [c.clause_id for c in clauses] == ["5"]
    assert "Annexes referenced by this clause" in clauses[0].body


def test_bare_letter_heading_is_not_parsed_as_annex_clause(make_docx):
    """A heading like 'A Note on Timer Handling' must not be mistaken for the
    annex clause id 'A' — a letter-led id requires at least one dot-numeric
    part (A.1, A.3.1.1). Regression for a false-positive-match risk."""
    path = make_docx("s.docx", [
        ("Heading 1", "5\tConnection control"),
        ("Normal", "Real body."),
        ("Heading 2", "A Note on Timer Handling"),
        ("Normal", "This text is not a clause id."),
    ])
    clauses = parse_leaf_clauses(path)
    assert [c.clause_id for c in clauses] == ["5"]
    assert "A Note on Timer Handling" in clauses[0].body
    assert "This text is not a clause id." in clauses[0].body


def test_unnumbered_subheading_text_is_folded_into_open_clause_body(make_docx):
    """A heading-styled paragraph that fails the clause-id pattern must not be
    discarded while a clause is open — its text joins the open clause's body."""
    path = make_docx("s.docx", [
        ("Heading 1", "5\tConnection control"),
        ("Normal", "First paragraph."),
        ("Heading 3", "Editor's note"),
        ("Normal", "Second paragraph."),
    ])
    clause = parse_leaf_clauses(path)[0]
    assert clause.body == "First paragraph.\n\nEditor's note\n\nSecond paragraph."


def test_table_in_clause_becomes_markdown_in_body(make_docx):
    path = make_docx("s.docx", [
        ("Heading 1", "5\tConnection control"),
        ("Normal", "Intro text."),
        ("Table", [
            ["Parameter", "Value", "Unit"],
            ["T310", "1000", "ms"],
            ["N310", "1", "count"],
        ]),
        ("Normal", "Trailing text."),
    ])
    clause = parse_leaf_clauses(path)[0]
    assert "| Parameter | Value | Unit |" in clause.body
    assert "| --- | --- | --- |" in clause.body
    assert "| T310 | 1000 | ms |" in clause.body
    assert "| N310 | 1 | count |" in clause.body
    header_line = next(line for line in clause.body.splitlines() if line.startswith("| Parameter"))
    assert header_line.index("Parameter") < header_line.index("Value") < header_line.index("Unit")


def test_body_paragraphs_are_joined_with_blank_lines(make_docx):
    path = make_docx("s.docx", [
        ("Heading 1", "5\tX"),
        ("Normal", "First."),
        ("Normal", "Second."),
    ])
    assert parse_leaf_clauses(path)[0].body == "First.\n\nSecond."
