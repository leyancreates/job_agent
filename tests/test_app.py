from doc_utils import extract_doc_id


def test_extract_doc_id():
    assert extract_doc_id("https://docs.google.com/document/d/abc123/edit") == "abc123"


def test_extract_doc_id_rejects_invalid_link():
    assert extract_doc_id("https://example.com/not-a-doc") == ""
