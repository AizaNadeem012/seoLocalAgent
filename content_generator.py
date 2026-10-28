import os
import re
import json
from pathlib import Path
from typing import Dict, Any, Optional

import requests
import database as db


def get_openai_api_key(target: Optional[Dict[str, Any]] = None, config: Optional[Dict[str, Any]] = None) -> str:
    """
    Retrieves the OpenAI API Key in order of precedence:
    1. Target's specific business profile
    2. Active business profile in database
    3. Global business_config
    4. os.environ['OPENAI_API_KEY']
    5. .env file in workspace
    """
    # 1. From target profile
    if target and target.get("business_profile_id"):
        try:
            p = db.get_business_profile_by_id(target["business_profile_id"], mask_passwords=False)
            if p and p.get("openai_api_key") and "••••" not in p["openai_api_key"]:
                return p["openai_api_key"].strip()
        except Exception:
            pass

    # 2. From active business profile
    try:
        active = db.get_active_business_profile(mask_passwords=False)
        if active and active.get("openai_api_key") and "••••" not in active["openai_api_key"]:
            return active["openai_api_key"].strip()
    except Exception:
        pass

    # 3. From config passed in
    if config and config.get("openai_api_key") and "••••" not in config["openai_api_key"]:
        return config["openai_api_key"].strip()

    # 4. From os.environ
    env_key = os.getenv("OPENAI_API_KEY", "").strip()
    if env_key:
        return env_key

    # 5. From .env file directly
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("OPENAI_API_KEY="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val:
                            return val
        except Exception:
            pass

    return ""


def generate_pitch_with_openai(
    api_key: str,
    site_name: str,
    target_url: str,
    niche: str,
    backlink: str,
    anchor: str,
    guidelines: str,
    sender_email: str
) -> Optional[Dict[str, str]]:
    """
    Uses OpenAI API (gpt-4o-mini / gpt-3.5-turbo) to write a hyper-personalized guest-post
    pitch email asking the editor for approval and requesting them to publish our guest post.
    """
    endpoint = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    system_prompt = (
        "You are an expert SEO outreach specialist and professional guest post contributor. "
        "Your goal is to write a highly compelling, polite, and persuasive outreach email to a website editor.\n\n"
        "CRITICAL REQUIREMENTS:\n"
        "1. Politely ask the editor for their approval and permission to allow us to submit a guest post to their website.\n"
        "2. Explicitly request the editor to publish our guest post on their platform, assuring them the article is 100% human-crafted, deeply researched, and tailored specifically to their audience.\n"
        "3. Propose 3 relevant, catchy article titles that fit their website niche and audience interests.\n"
        "4. Summarize the key value takeaways for their readers.\n"
        "5. Naturally integrate a contextual reference to the author's brand/portfolio using the anchor text and target URL provided.\n"
        "6. Keep the email concise, editorial, respectful, and easy for the editor to reply with 'Approved / Send draft'.\n"
        "7. Output ONLY a valid JSON object with keys 'subject' and 'body'. No markdown formatting outside JSON."
    )

    user_prompt = (
        f"Target Publication Name: {site_name}\n"
        f"Target Website URL: {target_url}\n"
        f"Target Niche / Topic: {niche}\n"
        f"Client Backlink Destination: {backlink}\n"
        f"Preferred Anchor Text: {anchor}\n"
        f"Client Guidelines & Info: {guidelines}\n"
        f"Outreach Email: {sender_email}\n\n"
        "Write the complete outreach email pitch requesting approval and publication now."
    )

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.7,
        "max_tokens": 1200
    }

    try:
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=25)
        if resp.status_code == 200:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            if "subject" in parsed and "body" in parsed:
                return {
                    "subject": parsed["subject"].strip(),
                    "body": parsed["body"].strip()
                }
    except Exception as e:
        print(f"[OpenAI Pitch Generation Fallback]: {e}")

    return None


def generate_article_with_openai(
    api_key: str,
    site_name: str,
    niche: str,
    backlink: str,
    anchor: str,
    guidelines: str
) -> Optional[Dict[str, Any]]:
    """
    Uses OpenAI API to craft an authoritative, unique ~800-1200 word guest article.
    """
    endpoint = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    system_prompt = (
        "You are an authoritative industry journalist and guest author. "
        "Write a comprehensive, publication-ready guest article formatted in Markdown (with H1, H2, bullet points, and an Author Bio). "
        "CRITICAL INSTRUCTIONS:\n"
        f"1. Naturally integrate the HTML backlink <a href=\"{backlink}\" target=\"_blank\" rel=\"noopener\">{anchor}</a> inside the body content where editorially relevant.\n"
        "2. Do NOT stuff keywords or write promotional fluff. Provide genuinely insightful, actionable industry analysis.\n"
        "3. Include a clean Author Bio at the bottom with a natural reference to the target backlink.\n"
        "4. Return ONLY a valid JSON object with keys 'title' (H1 article title) and 'body' (the full markdown content)."
    )

    user_prompt = (
        f"Target Publication: {site_name}\n"
        f"Industry Niche: {niche}\n"
        f"Backlink URL: {backlink}\n"
        f"Anchor Text: {anchor}\n"
        f"Content Guidelines & Topic Context: {guidelines}\n\n"
        "Generate the complete high-quality guest post article now."
    )

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.7,
        "max_tokens": 2500
    }

    try:
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=40)
        if resp.status_code == 200:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            title = parsed.get("title", f"The Future of {niche}")
            body = parsed.get("body", "")
            return {
                "title": title,
                "body": body,
                "word_count": len(body.split()),
                "has_anchor": anchor.lower() in body.lower(),
                "has_link": backlink.lower() in body.lower(),
                "niche": niche,
                "backlink_url": backlink,
                "anchor_text": anchor,
            }
    except Exception as e:
        print(f"[OpenAI Article Generation Fallback]: {e}")

    return None


class SmartContentGenerator:
    """
    Produces original, high-quality guest articles and personalized editorial pitches
    tailored to the target website's niche, audience, and guideline requirements.
    Supports OpenAI API when configured, with seamless built-in fallback.
    """

    def generate_article(
        self, 
        target: Dict[str, Any], 
        config: Dict[str, Any], 
        report: Dict[str, Any]
    ) -> Dict[str, Any]:
        niche = target.get("category") or report.get("niche_detected") or config.get("niche") or "Sustainable Fashion & Apparel"
        backlink = target.get("target_backlink_url") or config.get("backlink_url") or "https://www.afimahclothingstore.com"
        anchor = target.get("target_anchor_text") or config.get("anchor_text") or "sustainable luxury apparel"
        site_name = target.get("website_name") or report.get("website_title") or "Editorial Platform"
        guidelines = config.get("article_guidelines") or ""
        
        if site_name and len(site_name) > 35:
            site_name = site_name[:35].split("|")[0].strip()

        # Check if OpenAI API Key is available
        api_key = get_openai_api_key(target, config)
        if api_key:
            ai_article = generate_article_with_openai(
                api_key=api_key,
                site_name=site_name,
                niche=niche,
                backlink=backlink,
                anchor=anchor,
                guidelines=guidelines
            )
            if ai_article:
                return ai_article

        # Fallback: High-Quality Structured Template
        title = f"The New Paradigm in {niche}: Craftsmanship, Circular Innovation, and Digital Scalability"

        body = f"""# {title}

In an increasingly saturated global marketplace, organizations operating within **{niche}** face a defining crossroads. The conventional playbook—prioritizing rapid volume over enduring value—has yielded to an era governed by conscious consumers, stringent sustainability imperatives, and sophisticated digital craftsmanship. To thrive today, industry pioneers are reimagining how design, technology, and ethical responsibility intersect.

---

## 1. The Shifting Economics of Value in {niche}

Modern audiences no longer measure excellence solely by aesthetic novelty or superficial branding. Instead, consumer loyalty is anchored in substantive transparency, material authenticity, and verifiable longevity. The demand for ethical integrity has transitioned from an idealistic niche into an undeniable commercial baseline.

Leading market analysts highlight several key drivers accelerating this structural evolution:

- **Circular Material Innovation**: Transitioning from linear "take-make-waste" paradigms toward biodegradable textiles, low-impact dye processes, and regenerated fibers.
- **Traceable Value Chains**: Harnessing digital product passports and localized supply networks to provide uncompromised provenance from origin to point of sale.
- **Conscious Consumption**: Discerning buyers deliberately curating capsule collections designed to outlive ephemeral seasonal trends.

As market dynamics mature, brands that ground their operational identity in durable excellence cultivate durable brand equity.

---

## 2. Elevating Craftsmanship Through Sustainable Architecture

Building an enduring footprint within contemporary {niche.lower()} demands more than adopting eco-friendly nomenclature—it necessitates architectural refinement at every tier of creation. Precision patterning, bespoke finishing, and uncompromising material curation form the bedrock of this transformation.

Exemplifying this holistic standard, leaders championing <a href="{backlink}" target="_blank" rel="noopener">{anchor}</a> demonstrate how uncompromising aesthetic distinction harmonizes naturally with environmental stewardship. By fusing time-tested artisan tailoring with progressive low-waste fabrication, such forward-looking ateliers establish that luxury and sustainability are fundamentally reinforcing forces.

When foundational garments and accessories are engineered to resist physical and aesthetic obsolescence, they redefine consumer perceptions of value.

---

## 3. Digital Scalability and Community-Driven Engagement

While physical craftsmanship provides tangible integrity, digital transformation acts as the catalyst for widespread resonance. Leading enterprises in {niche.lower()} are successfully integrating bespoke commerce technologies to personalize client journeys:

1. **Virtual Fitting & Predictive Sizing**: Minimizing reverse logistics and carbon footprints by deploying computer-vision sizing algorithms.
2. **On-Demand & Small-Batch Manufacturing**: Eliminating overproduction through responsive inventory management and direct-to-consumer micro-drops.
3. **Transparent Brand Storytelling**: Engaging discerning communities through multimedia documentation of the design lifecycle and atelier craftsmanship.

---

## 4. Strategic Recommendations for Long-Term Resonance

For creative directors, enterprise strategists, and ambitious entrepreneurs navigating the evolving {niche.lower()} landscape, enduring success hinges on consistent execution across three vital pillars:

- **Prioritize Provenance Over Speed**: Resist the pressure of hyper-accelerated release cycles in favor of thoroughly vetted, durable collections.
- **Communicate Impact with Clarity**: Provide unambiguous certifications, lifecycle metrics, and authentic sustainability narratives.
- **Cultivate Authentic Industry Alliances**: Collaborate with ethical suppliers, digital innovators, and thought leaders who elevate communal standards.

---

## Conclusion & Key Takeaway

The future of {niche} will not be won by those who shout the loudest, but by those who build with the greatest depth and integrity. By uniting meticulous artisan techniques with progressive ecological benchmarks, forward-thinking creators are shaping a more conscious, resilient, and elevated cultural landscape.

---

### Author Bio
*Written by an industry strategist and contributing contributor specializing in sustainable enterprise, bespoke craftsmanship, and the evolution of global lifestyle markets. For inquiries or editorial collaborations, visit our portfolio at {backlink}.*
"""

        word_count = len(body.split())
        has_anchor = anchor.lower() in body.lower()
        has_link = backlink.lower() in body.lower()

        return {
            "title": title,
            "body": body,
            "word_count": word_count,
            "has_anchor": has_anchor,
            "has_link": has_link,
            "niche": niche,
            "backlink_url": backlink,
            "anchor_text": anchor,
        }

    def generate_pitch(
        self, 
        target: Dict[str, Any], 
        config: Dict[str, Any], 
        report: Dict[str, Any]
    ) -> Dict[str, str]:
        """
        Generates a tailored outreach email pitch to the editor.
        Explicitly asks for approval to submit a guest post and requests them to publish it.
        Uses OpenAI API if OPENAI_API_KEY is available; otherwise uses high-converting template.
        """
        niche = target.get("category") or report.get("niche_detected") or config.get("niche") or "Sustainable Fashion & Apparel"
        backlink = target.get("target_backlink_url") or config.get("backlink_url") or "https://www.afimahclothingstore.com"
        anchor = target.get("target_anchor_text") or config.get("anchor_text") or "sustainable luxury apparel"
        site_name = target.get("website_name") or report.get("website_title") or "Your Publication"
        target_url = target.get("website_url") or "https://yourwebsite.com"
        guidelines = config.get("article_guidelines") or ""
        sender_email = config.get("default_email", "outreach@afimahclothingstore.com")
        recipient = report.get("contact_email") or "editorial@target-domain.com"
        
        if site_name and len(site_name) > 30:
            site_name = site_name[:30].split("|")[0].strip()

        # Check if OpenAI API Key is available
        api_key = get_openai_api_key(target, config)
        if api_key:
            ai_pitch = generate_pitch_with_openai(
                api_key=api_key,
                site_name=site_name,
                target_url=target_url,
                niche=niche,
                backlink=backlink,
                anchor=anchor,
                guidelines=guidelines,
                sender_email=sender_email
            )
            if ai_pitch:
                ai_pitch["recipient"] = recipient
                ai_pitch["niche"] = niche
                return ai_pitch

        # Fallback: High-Converting Template that explicitly asks for approval and publication
        subject = f"Guest Post Contribution & Publication Request: Insights on {niche} for {site_name}"

        body = f"""Dear {site_name} Editorial Team,

I hope this email finds you well.

I have been following your publication's thoughtful coverage and high editorial standards. I am reaching out to respectfully ask for your approval to contribute an original, comprehensive guest post to {site_name}.

Given your audience's appreciation for in-depth, actionable analysis in the {niche} space, we have prepared unique insights that would provide immense value to your readers. If one of our proposed topics resonates with your upcoming editorial calendar, we kindly request you to allow us to submit our draft and publish our guest post on your esteemed platform.

### Proposed Article Titles for Your Approval:
1. **The New Paradigm in {niche}: Craftsmanship, Circular Innovation, and Digital Scalability**
2. **Beyond the Hype: How Sustainable Value Chains Are Redefining Modern {niche}**
3. **Strategic Blueprint: Integrating Artisan Tailoring and Sustainable Standards in {niche}**

### Summary of What We Offer:
- **100% Original & Human-Written**: Comprehensive, fact-checked analysis tailored specifically to match your word count, tone, and formatting guidelines.
- **Reader-Centric Value**: Concrete best practices, market data, and actionable frameworks that will keep your audience engaged.
- **Contextual Context**: Natural, editorially appropriate contextual citations, including a reference to {anchor} ({backlink}) as an illustrative industry example.
- **Zero Editorial Burden**: Our complete article is ready. We will happily adapt any section according to your feedback and editorial suggestions.

Could you please let us know if you approve one of these topics, or if you would like to see the full draft for review and publication?

Thank you very much for your time, consideration, and editorial guidance. We look forward to hearing from you.

Warm regards,

**Guest Post Contributor & Outreach Team**  
Email: {sender_email}  
Portfolio / Website: {backlink}
"""

        return {
            "subject": subject,
            "body": body,
            "recipient": recipient,
            "niche": niche,
        }


smart_content_generator = SmartContentGenerator()
