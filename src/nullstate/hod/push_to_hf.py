"""Push training dataset to HuggingFace. Called by HOD engine."""

import os
from huggingface_hub import HfApi

with open("src/wallet/.env") as f:
    for line in f:
        line = line.strip()
        if line.startswith("NULLSTATE_HF_TOKEN="):
            token = line.split("=", 1)[1].strip().strip("'\"")
            break
    else:
        print("ERROR: NULLSTATE_HF_TOKEN not found")
        exit(1)

api = HfApi(token=token)
api.upload_file(
    path_or_fileobj="src/training/nullstate_training_complete.jsonl",
    path_in_repo="data/nullstate_training_complete.jsonl",
    repo_id="NullStateV1/nullstate-training-data",
    repo_type="dataset",
    commit_message="Auto-update from HOD cycle"
)
print("Uploaded to HF")
