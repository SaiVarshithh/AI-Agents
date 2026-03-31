import requests
import json
import os

token = "hf_dummy" # Will just test 404 vs 401

models = [
    "Qwen/Qwen2.5-1.5B-Instruct",
    "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
    "microsoft/Phi-3-mini-4k-instruct",
    "facebook/bart-large-cnn",
]

urls = [
    "https://router.huggingface.co/hf-inference/models/{model}",
    "https://api-inference.huggingface.co/models/{model}",
]

for url_template in urls:
    print(f"\nTesting URL pattern: {url_template}")
    for model in models:
        url = url_template.format(model=model)
        try:
            r = requests.post(url, json={"inputs": "hi"}, headers={"Authorization": f"Bearer {token}"})
            print(f"{model}: {r.status_code}")
        except Exception as e:
            print(f"{model}: Error {e}")
