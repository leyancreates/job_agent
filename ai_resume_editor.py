"""Small command-line resume bullet editor."""

from google_docs_editor import Bullet, improve_bullets


def read_until_end(prompt: str) -> str:
    print(prompt)
    lines = []
    while True:
        line = input()
        if line == "END":
            return "\n".join(lines)
        lines.append(line)


def main() -> None:
    print("AI Resume Editor\n")
    job_description = read_until_end("Paste job description (type END to finish):")
    resume_text = read_until_end("\nPaste one resume bullet point (type END to finish):")
    result = improve_bullets(job_description, [Bullet(resume_text, 0, len(resume_text))])
    print("\nImproved version:\n")
    print(result[0])


if __name__ == "__main__":
    main()

