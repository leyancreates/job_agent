from google_docs_reader import get_google_services
from openai import OpenAI

client = OpenAI()

def get_bullet_paragraphs(doc_id):
    docs_service, _ = get_google_services()
    doc = docs_service.documents().get(documentId=doc_id).execute()

    results = []

    for element in doc["body"]["content"]:
        if "paragraph" not in element:
            continue

        paragraph = element["paragraph"]

        if "bullet" not in paragraph:
            continue

        text = ""
        start_index = None
        end_index = None

        for run in paragraph.get("elements", []):
            if "textRun" in run:
                text += run["textRun"]["content"]
                if start_index is None:
                    start_index = run["startIndex"]
                end_index = run["endIndex"]

        clean_text = text.strip()

        if clean_text:
            results.append({
                "text": clean_text,
                "start": start_index,
                "end": end_index
            })

    return results


def improve_bullets(job_description, bullets):
    original_text = "\n".join([f"- {b['text']}" for b in bullets])

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": """"
You are a professional resume editor.

Rules:
- Rewrite each bullet point only.
- Do NOT change the number of bullet points.
- Do NOT invent fake experience.
- Do NOT add tools, companies, degrees, or certifications not already mentioned.
- Keep each bullet VERY concise.
- Each bullet must be under 16 words.
- Do NOT mention AI unless the original bullet already mentions AI.
- Do NOT add phrases like "AI training", "AI model", or "AI systems" unless they already appear in the original resume.
- Return only the improved bullet text.
- One bullet per line.
"""
            },
            {
                "role": "user",
                "content": f"""
Job Description:
{job_description}

Original bullet points:
{original_text}

Rewrite these bullets to better match the job.
"""
            }
        ]
    )

    improved_text = response.choices[0].message.content

    improved_lines = [
        line.strip("-• ").strip()
        for line in improved_text.split("\n")
        if line.strip()
    ]

    return improved_lines


def replace_bullets_in_doc(doc_id, bullets, improved_lines):
    docs_service, _ = get_google_services()

    requests = []

    # 从后往前替换，避免 index 变化
    for bullet, new_text in zip(reversed(bullets), reversed(improved_lines)):
        start = bullet["start"]
        end = bullet["end"]

        requests.append({
            "deleteContentRange": {
                "range": {
                    "startIndex": start,
                    "endIndex": end - 1
                }
            }
        })

        requests.append({
            "insertText": {
                "location": {
                    "index": start
                },
                "text": new_text
            }
        })

    docs_service.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": requests}
    ).execute()


def tailor_google_doc(doc_id, job_description):
    bullets = get_bullet_paragraphs(doc_id)

    if not bullets:
        return "No bullet points found."

    improved_lines = improve_bullets(job_description, bullets)

    if len(improved_lines) != len(bullets):
        return "AI returned a different number of bullets. Please try again."

    replace_bullets_in_doc(doc_id, bullets, improved_lines)

    return f"Updated {len(bullets)} bullet points in Google Docs."
