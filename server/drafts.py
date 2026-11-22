"""Draft generation: follow-up post (after a flag), review post, sponsor pitch.
Rules (PRD 9.5): only facts from the check result; 'recalled' only with a confirmed official action; disclosure line
on affiliate/sponsored drafts; no invented contacts/emails/prices."""
import json

from . import llm


def _basis(check):
    confirmed = [a for a in check["official_actions"] if a["match"] == "confirmed"]
    return confirmed, (confirmed or check["official_actions"])


def follow_up(item, check):
    confirmed, basis = _basis(check)
    posts = item.get("posts_count", 0)
    prompt = f"""A parenting creator linked "{item['name']}" (affiliate link) in {posts} post(s). A safety check flagged it.
Verdict: {check['verdict']} ({'official action confirmed' if confirmed else 'possible match or allegations only'}).
<retrieved_data>
Official actions found: {json.dumps(basis, indent=1)[:2500]}
Allegations: {json.dumps(check['allegations'], indent=1)[:1500]}
</retrieved_data>

Write the creator's follow-up for their followers. Calm, accountable, warm, first person, no panic, no medical or legal claims.
Use ONLY facts above. If the match is only "possible" or the issue is allegations, do NOT say the product was recalled: say safety concerns were raised and point followers to the official source.
Include: stop-use / check-the-recall-page guidance only as supported by the sources, the remedy only if listed, that the affiliate link is being removed, and the official URL.
Return JSON: {{"post_caption": str (under 150 words), "story_script": [3 short lines], "comment_reply": str (under 40 words)}}"""
    d = llm.claude_json(prompt, 1200)
    return {"post_caption": d.get("post_caption", ""), "story_script": [str(x) for x in (d.get("story_script") or [])][:4],
            "comment_reply": d.get("comment_reply", "")}


def review_post(item, check, profile):
    prompt = f"""Draft a review post for a parenting creator about "{item['name']}".
Creator: {json.dumps(profile)}
Safety check ({check['verdict']}, checked {check['checked_on']}): {check['headline']}
Safety note: {check['safety_note']}
Gaps: {check['gaps']}

Write a short, honest post draft. Include a one-line safety mention (what was checked: CPSC recalls and warnings; "not a guarantee of safety"), and a clear disclosure line for affiliate or sponsored content (e.g. "Affiliate link: I may earn a commission"). No medical claims. Do not invent product features, prices or statistics: use placeholders like [what you liked] where details are missing.
Return JSON: {{"caption": str (under 150 words), "story_script": [3 short lines]}}"""
    d = llm.claude_json(prompt, 1200)
    return {"caption": d.get("caption", ""), "story_script": [str(x) for x in (d.get("story_script") or [])][:4]}


def sponsor_pitch(item, check, profile):
    ok = check["verdict"] == "no_issues_found"
    prompt = f"""Draft a sponsorship pitch email from a parenting creator to the brand behind "{item['name']}" ({item.get('brand') or 'brand unknown'}).
Creator profile: {json.dumps(profile)}
Rules: address "the partnerships team" generally; NO invented names or email addresses; do not invent brand facts, campaigns, prices or statistics (use placeholders like [specific detail about the brand] if needed); under 170 words; clear ask; sign off with the handle or "[Your name]".
{'You may add one sentence saying you checked CPSC recalls and warnings before pitching.' if ok else 'Do NOT mention any safety check.'}
Return JSON: {{"subject": str, "body": str}}"""
    d = llm.claude_json(prompt, 1000)
    return {"subject": d.get("subject", ""), "body": d.get("body", ""), "partnership_page_url": None}
