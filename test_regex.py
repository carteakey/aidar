import re
text = "It's not merely a tool, but a platform. It's not a bug. It's a feature. This serves as a reminder that we must quietly orchestrate the tapestry of our workflows. Not because it is easy, but because it is right."

patterns = [
    r"\b(?:it'?s not|it is not|\w+ isn'?t|\w+ aren'?t)\b[^.,:;—–\n]{1,80}[.,:;—–\s]\s*(?:but\b|it'?s\b|it is\b|they'?re\b|they are\b|rather\b)",
    r"\bnot because\s+[^.,:;—–\n]{1,80}[.,:;—–\s]\s*but because\b",
    r"\bnot (?:just|merely|simply|only)?\s*[^.,:;—–\n]{1,60}[.,:;—–\s]\s*but (?:rather|instead|also)?\s*\b"
]

for p in patterns:
    r = re.compile(p, re.IGNORECASE)
    print("Pattern:", p)
    print("Matches:", r.findall(text))
    print()
