import zipfile
import os

# 압축할 대상 디렉토리
src_dir = './'
# 결과물 ZIP 파일 경로
output_zip = 'tajo-app.zip'

# 제외할 패턴 목록
exclude_patterns = [
    '.DS_Store', '.pyc', '.pyo', '__pycache__', '.sqlite3', '.env',
    '.git', '.idea', '.vscode', 'venv', 'tajo_env'
]

def should_exclude(file_path):
    for pattern in exclude_patterns:
        if pattern in file_path.replace("\\", "/"):
            return True
    return False

os.makedirs('deploy', exist_ok=True)

with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
    for foldername, subfolders, filenames in os.walk(src_dir):
        for filename in filenames:
            file_path = os.path.join(foldername, filename)
            rel_path = os.path.relpath(file_path, src_dir)
            if not should_exclude(rel_path):
                zipf.write(file_path, rel_path)

print(f'압축 완료: {output_zip}')