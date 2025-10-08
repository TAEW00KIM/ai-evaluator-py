import os
from pydantic import BaseModel

class BaseSettings(BaseModel):
    spring_callback_url: str
    spring_status_update_url: str
    upload_base_dir: str
    secret_dataset_path: str

class LocalSettings(BaseSettings):
    spring_callback_url: str = "http://localhost:8080/api/internal/submissions/{submissionId}/complete"
    spring_status_update_url: str = "http://localhost:8080/api/internal/submissions/{submissionId}/running"
    upload_base_dir: str = "/Users/twkk0/Desktop/AutoGrader/AutoGrader/uploads" # ◀️ 내 PC의 uploads 폴더 경로
    secret_dataset_path: str = "path/to/local/dummy_dataset.csv" # ◀️ 내 PC의 테스트용 데이터셋 경로

class ProdSettings(BaseSettings):
    spring_callback_url: str = "http://<교수님 서버 IP>:8080/api/internal/submissions/{submissionId}/complete"
    spring_status_update_url: str = "http://<교수님 서버 IP>:8080/api/internal/submissions/{submissionId}/running"
    upload_base_dir: str = "/home/ubuntu/ai-evaluator-be/uploads" # ◀️ 서버의 uploads 폴더 경로
    secret_dataset_path: str = "/home/ubuntu/secret_dataset/mnist_test.csv" # ◀️ 서버의 비밀 데이터셋 경로

def get_settings():
    app_env = os.getenv("APP_ENV", "local") # 환경변수 APP_ENV를 읽어옴, 없으면 'local'
    if app_env == "prod":
        return ProdSettings()
    return LocalSettings()

settings = get_settings()