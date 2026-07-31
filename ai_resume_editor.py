from openai import OpenAI

client = OpenAI()

print("AI Resume Editor\n")

# 输入岗位 JD
print("Paste job description (type END to finish):")
lines = []
while True:
    line = input()
    if line == "END":
        break
    lines.append(line)

job_description = "\n".join(lines)

# 输入你简历的一段（先测试一小段）
print("\nPaste ONE resume bullet point (type END to finish):")
lines = []
while True:
    line = input()
    if line == "END":
        break
    lines.append(line)

resume_text = "\n".join(lines)

print("\n--- AI Improving Resume ---\n")

# 调用 AI
response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {
            "role": "system",
            "content": """
You are a professional resume editor.

IMPORTANT RULES:
- Do NOT invent fake experience.
- Only rewrite based on the given resume.
- Do NOT add new roles or jobs.
- Keep it realistic and truthful.
- Make it concise and professional.

Your goal:
Improve the resume bullet point to better match the job description,
while keeping the original meaning.
"""},
        {
            "role": "user",
            "content": f"""
Job Description:
{job_description}

Resume Bullet Point:
{resume_text}

Task:
Rewrite this bullet point to better match the job.

Rules:
- Keep it ONE bullet point
- Do NOT create new experience
- Do NOT change facts
- Make it stronger and more relevant
"""
        }
    ]
)

print("Improved Version:\n")
print(response.choices[0].message.content)
