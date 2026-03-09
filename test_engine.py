from pathlib import Path
from aidar.core.analyzer import Analyzer
from aidar.patterns.loader import load_patterns, load_weight_config
from aidar.patterns.registry import PatternRegistry
from aidar.core.scorer import compute_aggregate
from aidar.models.config import AppConfig

text = "It's not merely a tool, but a platform. It's not a bug. It's a feature. This serves as a reminder that we must quietly orchestrate the tapestry of our workflows. Imagine a world where this fundamentally reshapes the paradigm. The reality is simpler: we delve into synergy. Despite these challenges, let's break this down."

patterns = load_patterns(Path("patterns"))
registry = PatternRegistry(patterns)
analyzer = Analyzer(registry)
config = AppConfig(patterns_dir="patterns", weights=load_weight_config(Path("patterns")))

word_count = len(text.split())
vector = analyzer.run(text, word_count)
agg = compute_aggregate(vector, config, word_count=word_count)

print("Aggregate Score:", agg.aggregate_score)
print("\nTropes Category Score:", vector.tropes)
print("\nIndividual Tropes Results:")
for r in vector.results_by_category("tropes"):
    if r.raw_value > 0:
        print(f"  - {r.pattern_id}: {r.normalized_score:.2f} ({r.label})")

print("\nIndividual Vocabulary Results:")
for r in vector.results_by_category("vocabulary"):
    if r.raw_value > 0:
        print(f"  - {r.pattern_id}: {r.normalized_score:.2f} ({r.label})")
