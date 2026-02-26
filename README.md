# aidar

AI text detection via stylistic anomaly scoring.

Detects AI-generated content on websites using known stylistic signals — em dash overuse, hedging phrases, bullet point density, AI vocabulary idioms, and more. Outputs a per-category score vector and a 0–100 aggregate score.

## Quick start

```bash
pip install -e .
aidar analyze https://example.com
aidar compare https://site1.com https://site2.com
aidar scan --batch urls.txt --save
```

## Pattern repository

Patterns live in `patterns/` as YAML files. Add new signals by creating a YAML file in the appropriate category directory.
# aidar
