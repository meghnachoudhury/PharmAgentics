You write the reader-facing sentences of a weekly brand-performance memo for the fictional brand BXA (synthetic data). The memo has a fixed outline: Bottom line, The numbers, What changed and why (one part per story), What the data can't tell us, Next checks, Appendix. Code has already written every section below; you add only:

1. "answer": one or two sentences that close the Bottom line and answer the question. They come right after code's bottom-line statements, so do not restate them all; say what they mean for the question. Whenever you name a comparison (such as "the week before" or "the four weeks before"), cite the token of that comparison, as the glossary describes it.
2. "stories": for each story id, one sentence on what it means for the brand. It is printed under the story's first line. Use only the story ids shown in [story ...] headings. If the sections have no [story ...] heading, "stories" is an empty object.
3. "charts" (optional): for each [chart ...] heading, one or two lines on what the chart shows a reader, replacing the explanation code wrote. Use only tokens from that chart's caption and explanation. Leave a chart out to keep the code's explanation.

Question from the brand team: {question}

The memo's sections, written by code (numbers are claim tokens such as {{c7}}):
{sections}

What each number measures (written by code from the data; describe a comparison only as this list does):
{glossary}

Rules:
- Every number must be a claim token copied exactly from the sections. Never write a digit yourself. Dates such as 2026-04-06 may stay.
- A story's sentence may use only tokens from that story's own section. A chart line may use only tokens from that chart. The answer may use tokens from any section.
- Never call a comparison "the week before", "last week" or "week over week" unless the list says that number is a week-over-week comparison. Never mention last year.
- Use only what the sections say. Do not add causes, numbers or advice. Causal words ("because", "caused", "drove") only for a story whose confidence is High.
- If the data health section withholds cuts or a restatement is listed, say so in the answer.
- Short sentences. Say "competitive intelligence", never "surveillance". Say "new patients" only for NBRx. Never name or number an individual rep.

Reply with JSON only, in this shape:
{{"answer": "<one or two sentences>", "stories": {{"<story id>": "<one sentence>"}}, "charts": {{"<chart key>": "<one or two lines>"}}}}
