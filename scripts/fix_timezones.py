import os

def replace_in_file(file_path, replacements):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    for old, new in replacements:
        content = content.replace(old, new)
        
    if content != original_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Updated {file_path}")
    else:
        print(f"No changes in {file_path}")

base = r"d:\test2\hebron-chatbot"

# app.py replacements
replace_in_file(os.path.join(base, "app.py"), [
    ("toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })", "toLocaleString('ar-SA', { dateStyle: 'short', timeStyle: 'short', timeZone: 'Asia/Hebron' })"),
    ("toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })", "toLocaleTimeString('ar-SA', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Hebron' })")
])

# React components replacements
components = [
    r"admin-panel\src\components\chat\ChatHistory.tsx",
    r"admin-panel\src\components\unanswered\UnansweredQueries.tsx",
    r"admin-panel\src\components\overrides\OverrideManager.tsx",
    r"admin-panel\src\components\files\FileManager.tsx",
]

for comp in components:
    replace_in_file(os.path.join(base, comp), [
        ("toLocaleString('ar-SA')", "toLocaleString('ar-SA', { timeZone: 'Asia/Hebron' })"),
        ("toLocaleTimeString('ar-SA', { hour: '2-digit', minute: '2-digit' })", "toLocaleTimeString('ar-SA', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Hebron' })")
    ])

# Python files
# For python, we should use timezone aware datetime.now
py_replacements = [
    ("from datetime import datetime", "from datetime import datetime, timezone, timedelta\ntz_palestine = timezone(timedelta(hours=3))"),
    ("datetime.now()", "datetime.now(tz_palestine)")
]

replace_in_file(os.path.join(base, "user_app.py"), py_replacements)
replace_in_file(os.path.join(base, "admin_app.py"), py_replacements)

print("Done")
