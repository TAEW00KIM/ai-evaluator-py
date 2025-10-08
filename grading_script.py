import json

# 간단히 성공 결과를 출력하는 테스트 스크립트
result = {
    "score": 88.8,
    "log": "테스트 채점 스크립트 실행 성공!"
}
print(json.dumps(result))