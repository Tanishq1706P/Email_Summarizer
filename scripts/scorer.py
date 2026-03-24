import json
import re

def score_json(input_json, output_json):
    with open(input_json, 'r', encoding='utf-8') as f:
        emails = json.load(f)

    for email in emails:
        score = 0
        body = email.get('body', '').lower()
        subject = email.get('subject', '').lower()

        # High priority keywords
        urgent_keywords = ['urgent', 'asap', 'immediately', 'deadline', 'action required', 'important']
        if any(kw in body for kw in urgent_keywords) or any(kw in subject for kw in urgent_keywords):
            score += 5

        # Financial keywords
        fin_keywords = ['invoice', 'payment', 'budget', 'amount', 'usd', 'cost', 'price']
        if any(kw in body for kw in fin_keywords):
            score += 3

        # Question detection
        if '?' in body:
            score += 2

        email['priority_score'] = score
        email['priority'] = 'High' if score >= 5 else 'Normal' if score >= 2 else 'Low'

    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(emails, f, indent=2, ensure_ascii=False)
    
    print(f"Priority scoring complete. Scored {len(emails)} emails.")
