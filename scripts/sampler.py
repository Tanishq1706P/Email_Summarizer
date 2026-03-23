import json
import random
from collections import defaultdict

class StratifiedSampler:
    def __init__(self, seed=42):
        random.seed(seed)

    def stratified_sample_json(self, input_json, output_json, sample_per_strata=10, strata_key='from'):
        with open(input_json, 'r', encoding='utf-8') as f:
            emails = json.load(f)

        strata = defaultdict(list)
        for email in emails:
            key = email.get(strata_key, 'unknown')
            strata[key].append(email)

        sampled_emails = []
        for key in strata:
            items = strata[key]
            if len(items) <= sample_per_strata:
                sampled_emails.extend(items)
            else:
                sampled_emails.extend(random.sample(items, sample_per_strata))

        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump(sampled_emails, f, indent=2, ensure_ascii=False)
        
        print(f"Stratified sampling complete. Sampled {len(sampled_emails)} from {len(emails)} emails.")
