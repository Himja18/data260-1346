## Analysis

All three chunking strategies achieved a 100% hit rate (5/5 questions had a correct source
document somewhere in their top-3 retrieved chunks), but top-1 precision diverged meaningfully.
Token-based chunking (512-token windows, 50-token overlap) was the most consistently precise,
landing the correct primary source at rank 1 for all 5 questions. Semantic chunking matched that
on 4 of 5, but on the multi-source question (q3) its top-1 chunk came from a derived
cross-reference file we wrote ourselves rather than one of the three primary FTA documents the
question actually depends on — a reasonable retrieval given that file exists specifically to
summarize the fact being asked about, but not what a strict "did it find the primary source"
metric wants to see. Sentence-window chunking (window size 3) was the least top-1-precise,
landing on a cross-reference summary instead of a primary source at rank 1 for both q3 and q4,
with the correct primary document only appearing at rank 2 or 3. This matches its underlying
mechanism: because each node is built around a single sentence, a short, cleanly-phrased
sentence in one of our own synthesis files can out-score a longer, more verbose passage in the
actual government report, even when the report is the "right" answer.

The adversarial question (q4) is the most informative test in this set: it was built specifically to
see whether dense shared vocabulary across three separate WMATA incidents (L'Enfant Plaza,
Fort Totten, Shady Grove) would fool a chunker into retrieving the wrong incident's facts with
high confidence. None of the three pipelines fell into that trap — Fort Totten never outranked
L'Enfant Plaza in any pipeline's top 3, and token chunking in particular showed a clear
discrimination margin (0.382 vs. 0.662 L2 distance between rank 1 and rank 3). This suggests
the underlying embedding model (BAAI/bge-small-en-v1.5) captures enough incident-specific
detail (dates, casualty counts, specific causes) to separate similar-sounding accidents, regardless
of which chunking strategy delivers the text to it.

## Conclusion

For this corpus and question set, token-based chunking delivered the most reliable top-1
retrieval precision, while sentence-window chunking, despite producing far more granular nodes
(999 vs. 117), was the most prone to surfacing a concise secondary summary over the primary
source document at rank 1. Semantic chunking sat between the two, trading roughly 4x the
indexing time of token chunking for chunk boundaries that follow topic shifts rather than a fixed
token count. If retrieval precision at rank 1 matters most for a downstream use case, token-based
chunking is the safer default here; if minimizing chunk count and indexing time matters more,
token-based chunking wins on that axis too, making it the strongest overall choice for this
particular domain and corpus.