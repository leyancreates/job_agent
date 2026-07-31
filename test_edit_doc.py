from google_docs_editor import tailor_google_doc

doc_id = "1469NlpqHa7pnvCEudLRMZs8mZRLMEXQerZge9_JCwic"

job_description = """
This role requires data analysis, attention to detail, communication, Excel, reporting, and teamwork.
"""

result = tailor_google_doc(doc_id, job_description)

print(result)
