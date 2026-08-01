"""Manual smoke test. Set TEST_GOOGLE_DOC_ID before running."""

import os

from google_docs_editor import preview_tailoring


def main() -> None:
    doc_id = os.getenv("TEST_GOOGLE_DOC_ID")
    if not doc_id:
        raise SystemExit("Set TEST_GOOGLE_DOC_ID to run this manual test.")
    bullets, improved = preview_tailoring(
        doc_id,
        "This role requires data analysis, attention to detail, Excel, reporting, and teamwork.",
    )
    for original, suggestion in zip(bullets, improved):
        print(f"- {original.text}\n+ {suggestion}\n")


if __name__ == "__main__":
    main()

