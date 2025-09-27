#!/usr/bin/env python3
import os
import sys
import argparse
import re

# ----- Heuristic fallback (no API key needed) -----
FILLERS = {"basically","like","literally","actually","kind of","sort of","you know"}
LEADING_JUNK = re.compile(r"^\s*[-•*>\d.)\]]+\s*")
SPACES = re.compile(r"\s+")
TRAILING_PUNCT = re.compile(r"[.!?…]+$")

def rule_concise(text: str) -> str:
    # Take first non-empty line as the main thought
    line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    if not line:
        return ""

    # Strip leading bullets/numbers, collapse spaces
    line = LEADING_JUNK.sub("", line)
    line = SPACES.sub(" ", line)

    # Remove very common fillers (whole-word)
    def drop_fillers(s: str) -> str:
        for f in sorted(FILLERS, key=len, reverse=True):
            s = re.sub(rf"\b{re.escape(f)}\b", "", s, flags=re.IGNORECASE)
            s = SPACES.sub(" ", s)
        return s.strip()

    line = drop_fillers(line)

    # If it's a noun phrase, gently add a copula
    # (very light guess: no verb present and starts with a noun/pronoun/article)
    tokens = line.split()
    has_verb = any(re.search(r"\b(am|is|are|was|were|be|being|been|do|does|did|have|has|had|can|could|will|would|shall|should|may|might|must|[a-zA-Z]+ed|[a-zA-Z]+ing)\b", line, re.I))
    if tokens and not has_verb:
        # Insert "is" after the first token if it reads like a subject phrase
        if re.match(r"^(the|a|an|this|that|these|those|my|our|their|his|her|its|we|i|you|they|he|she|it)\b", tokens[0], re.I):
            line = tokens[0] + " is " + " ".join(tokens[1:])
        else:
            line = "This is " + line

    # Capitalize first letter (respect leading quotes)
    def cap_first(s: str) -> str:
        m = re.match(r'^(\W*)(\w)(.*)$', s)
        if not m: return s
        pre, ch, rest = m.groups()
        return pre + ch.upper() + rest
    line = cap_first(line)

    # Add terminal punctuation if missing
    if not TRAILING_PUNCT.search(line):
        line += "."

    # Clean space before punctuation
    line = re.sub(r"\s+([,;:.!?])", r"\1", line)

    return line.strip()

# ----- OpenAI (AI mode) -----
def ai_concise(text: str, level: str = "standard") -> str:
    """
    Requires env var OPENAI_API_KEY. Uses OpenAI Responses API.
    """
    from openai import OpenAI  # pip install openai>=1.0

    client = OpenAI(api_key="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")

    styles = {
        "light": "Only fix casing, spacing, and add the fewest necessary words to make one grammatical sentence.",
        "standard": "Rewrite into one concise, natural sentence. Add minimal glue words if needed.",
        "heavy": "Strongly tighten wording but preserve meaning; output exactly one sentence."
    }
    style = styles.get(level, styles["standard"])

    prompt = (
        "You turn any input (fragments, bullet points, messy notes) into exactly ONE concise, "
        "well-formed English sentence. Only add minimal glue words needed for grammar; do not add new facts. "
        "Preserve names, numbers, URLs, code/text tokens as-is. No preambles, no quotes—return just the sentence.\n\n"
        f"Guidance: {style}\n\n"
        f"Input:\n{text}\n\nOutput (one sentence only):"
    )

    resp = client.responses.create(
        model="gpt-4o-mini",  # or another text-capable model you have access to
        input=prompt,
        max_output_tokens=100,
    )

    # Prefer the convenience accessor if available; else parse
    out = getattr(resp, "output_text", None)
    if not out:
        try:
            # Fallback extraction
            parts = []
            for item in resp.output:
                for c in getattr(item, "content", []):
                    if getattr(c, "type", "") == "output_text":
                        parts.append(getattr(c, "text", ""))
            out = " ".join(parts).strip()
        except Exception:
            out = ""

    # Enforce single sentence & cleanup, just in case
    out = out.strip()
    out = re.sub(r"\s+", " ", out)
    # If the model gave multiple sentences, take the first clause ending in . ! ?
    m = re.search(r"(.+?[.!?])(\s|$)", out)
    if m:
        out = m.group(1).strip()
    if out and not TRAILING_PUNCT.search(out):
        out += "."

    return out

def concise(text: str, level: str) -> str:
    if os.environ.get("OPENAI_API_KEY"):
        try:
            return ai_concise(text, level)
        except Exception as e:
            # Graceful fallback
            return rule_concise(text)
    return rule_concise(text)

def polish_text(inputText):
    return concise(inputText, "standard")

def main():
    p = argparse.ArgumentParser(description="Make input into ONE concise, well-formed sentence.")
    p.add_argument("text", nargs="?", help="Text to condense. If omitted, reads from stdin.")
    p.add_argument("--level", choices=["light","standard","heavy"], default="standard", help="Concision strength.")
    args = p.parse_args()

    # raw = args.text if args.text is not None else sys.stdin.read()
    # print(concise(raw, args.level))
    print(polish_text("[hi, hi, hi, hi, hi, hi, hi, bye, bye, hi, hi, hi, hi, no, hi, hi, hi, bye, hi, "
         + "hi, yes, no, no, hi, hi, my, my, my, my, my, my, my, my, your, my, my, my, eye, my, my, name, name, name, "
         + "name, name, hi, name, name, the, name, name, name, is, is, is, is, is, not, is, is, is, is, not, is, is, is, "
         + "is, is, is, is, is, John, John, John, John, John, good, John, John, John, John, John, John, John, John]"))

if __name__ == "__main__":
    main()
