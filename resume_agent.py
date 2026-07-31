# resume_agent.py

print("Welcome to Resume Agent!\n")

print("Paste job description below.")
print("Type END when finished:\n")

lines = []

while True:
    line = input()
    if line == "END":
        break
    lines.append(line)

job_description = "\n".join(lines).lower()

print("\n--- Detecting Job Type ---")

# 判断岗位类型
if "gis" in job_description or "arcgis" in job_description:
    job_type = "GIS"
elif "data" in job_description or "sql" in job_description:
    job_type = "Data"
elif "ai" in job_description and "annotator" in job_description:
    job_type = "AI Trainer"
else:
    job_type = "General"

print(f"Job Type: {job_type}")

# 不同岗位 → 不同技能
skill_map = {
    "GIS": ["GIS", "ArcGIS", "Remote Sensing", "Python", "Spatial Analysis"],
    "Data": ["Python", "SQL", "Excel", "Statistics", "Data Analysis"],
    "AI Trainer": ["English", "Writing", "Communication", "Attention to detail", "Feedback"],
    "General": ["Communication", "Teamwork", "Problem solving"]
}

your_skills = skill_map[job_type]

print("\n--- Analysis Result ---")

matched = []
missing = []

for skill in your_skills:
    if skill.lower() in job_description:
        matched.append(skill)
    else:
        missing.append(skill)

print(f"\nMatched Skills ({len(matched)}):")
for s in matched:
    print(f"✔ {s}")

print(f"\nMissing Skills ({len(missing)}):")
for s in missing:
    print(f"✘ {s}")

score = int(len(matched) / len(your_skills) * 100)

print(f"\nMatch Score: {score}%")

if score > 70:
    print("🔥 Strong match! Apply!")
elif score > 40:
    print("⚠️ Medium match. Tailor resume.")
else:
    print("❌ Weak match.")

print("\n--- Suggestions ---")

if job_type == "AI Trainer":
    print("\nTo improve your resume for this role:")
    print("1. Emphasize English writing and communication skills.")
    print("2. Mention any experience giving feedback or evaluating content.")
    print("3. Highlight attention to detail in your projects.")
    print("4. If possible, add experience related to AI tools or ChatGPT usage.")

elif job_type == "Data":
    print("\nTo improve your resume for this role:")
    print("1. Add SQL and Python projects.")
    print("2. Show data analysis or dashboard experience.")
    print("3. Mention statistics or modeling work.")

elif job_type == "GIS":
    print("\nTo improve your resume for this role:")
    print("1. Highlight ArcGIS / spatial analysis experience.")
    print("2. Add remote sensing or mapping projects.")
    print("3. Mention any Python (geopandas) usage.")

else:
    print("\nGeneral advice:")
    print("1. Improve communication and teamwork examples.")
    print("2. Show problem-solving experience.")
