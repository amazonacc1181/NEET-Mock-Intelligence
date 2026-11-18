from core.pdf_pipeline import split_questions


def test_split_questions_preserves_question_numbers_and_options():
    pages = [{
        "page_number": 1,
        "image_path": None,
        "text": """1. A body is moving with speed 10 m/s. Find momentum.\n(A) 10 kg m/s\n(B) 20 kg m/s\n(C) 5 kg m/s\n(D) 2 kg m/s\n\n2) Which of the following is correct?\n(A) First\n(B) Second\n(C) Third\n(D) Fourth\n""",
    }]
    questions, warnings = split_questions(pages, "abc123", "mock")
    assert len(questions) == 2
    assert questions[0]["question_number"] == 1
    assert questions[0]["question_ordinal"] == 1
    assert questions[0]["options"]["A"] == "10 kg m/s"
    assert questions[1]["question_number"] == 2
    assert questions[1]["options"]["D"] == "Fourth"


def test_split_questions_supports_restarted_question_numbers():
    pages = [{
        "page_number": 1,
        "image_path": None,
        "text": "1. Physics question statement here.\n2. Physics second question statement here.\n" ,
    }, {
        "page_number": 2,
        "image_path": None,
        "text": "1. Chemistry question statement here.\n2. Chemistry second question statement here.\n",
    }]
    questions, warnings = split_questions(pages, "paper", "mock")
    assert len(questions) == 4
    assert [q["question_number"] for q in questions] == [1, 2, 1, 2]
    assert [q["question_ordinal"] for q in questions] == [1, 2, 3, 4]
    assert questions[0]["subject"] == "Physics"
    assert questions[2]["subject"] == "Physics"  # ordinal-based subject heuristic; review for non-standard paper layout


def test_split_questions_supports_number_marker_on_own_line():
    pages = [{
        "page_number": 1,
        "image_path": None,
        "text": """1.\nA particle moves with constant acceleration. Find its final velocity.\n(A) 2 m/s\n(B) 4 m/s\n(C) 6 m/s\n(D) 8 m/s\n2.\nWhich statement about DNA is correct?\n(A) It contains uracil\n(B) It is usually double stranded\n(C) It is made of amino acids\n(D) It contains ribose\n""",
    }]
    questions, warnings = split_questions(pages, "standalone", "mock")
    assert len(questions) == 2
    assert questions[0]["question_number"] == 1
    assert questions[0]["question_text"].startswith("A particle moves")
    assert questions[0]["options"]["A"] == "2 m/s"
    assert questions[1]["question_number"] == 2
    assert questions[1]["question_text"].startswith("Which statement")