from github import Github, Auth
import os

auth = Auth.Token("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")
g = Github(auth=auth)
repo = g.get_repo("jumadijava/CMM-QUALITY-DASHBOARD")

folder_lokal = "D:/cmm-dashboardv4"

for root, dirs, files in os.walk(folder_lokal):
    for file in files:
        filepath = os.path.join(root, file)
        with open(filepath, "rb") as f:
            content = f.read()
        
        repo_path = filepath.replace(folder_lokal, "").replace("\\", "/").lstrip("/")
        
        try:
            existing = repo.get_contents(repo_path)
            repo.update_file(repo_path, "update file", content, existing.sha)
        except:
            repo.create_file(repo_path, "upload file", content)

print("Done!")