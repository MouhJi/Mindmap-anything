"""Section-aware source-preserving chunking with an offline UTF-8 byte tokenizer.

Byte tokens are exact, conservative budget units, NOT estimates of a model's BPE
tokens. No encoding downloads or model-specific tokenizer are required.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import re

from markdown_it import MarkdownIt
from pydantic import Field

from .models import SourceChunk, stable_id


@dataclass(frozen=True, init=False)
class ChunkingConfig:
    max_bytes: int = 4096
    overlap_bytes: int = 256
    relevance_enabled: bool = True
    exclude_obvious_nontechnical: bool = True

    def __init__(self, max_tokens=4096, overlap_tokens=256, *, max_bytes=None,
                 overlap_bytes=None, relevance_enabled=True, exclude_obvious_nontechnical=True):
        # Legacy arguments remain accepted; new configurations name actual units.
        object.__setattr__(self, 'max_bytes', max_tokens if max_bytes is None else max_bytes)
        object.__setattr__(self, 'overlap_bytes', overlap_tokens if overlap_bytes is None else overlap_bytes)
        object.__setattr__(self, 'relevance_enabled', relevance_enabled)
        object.__setattr__(self, 'exclude_obvious_nontechnical', exclude_obvious_nontechnical)
        self.__post_init__()

    @property
    def max_tokens(self):
        return self.max_bytes

    @property
    def overlap_tokens(self):
        return self.overlap_bytes

    def __post_init__(self):
        if type(self.max_tokens) is not int or self.max_tokens < 32:
            raise ValueError('max_tokens must be an integer >= 32')
        if type(self.overlap_tokens) is not int or not 0 <= self.overlap_tokens < self.max_tokens:
            raise ValueError('overlap_tokens must be smaller than max_tokens')


class SectionChunk(SourceChunk):
    section_title: str
    heading_path: list[str]
    metadata: dict = Field(default_factory=dict)
    start_char: int
    end_char: int
    overlap_prefix: str = ''
    token_count: int
    tokenizer: str = 'utf8-byte-v1'
    oversized_reason: str | None = None
    context_warnings: list[str] = Field(default_factory=list)
    document_title: str = ''
    byte_count: int = 0
    extraction_eligible: bool = True
    eligibility_reasons: list[str] = Field(default_factory=list)
    content_relevance: str = 'unclassified'
    relevance_reasons: list[str] = Field(default_factory=list)

    def extraction_context(self) -> dict:
        return dict(document_title=self.document_title, heading_path=list(self.heading_path),
                    section_title=self.section_title, content=self.text)

    def as_source_chunk(self) -> SourceChunk:
        return SourceChunk.model_validate({name: getattr(self, name) for name in SourceChunk.model_fields})


def count_tokens(text: str) -> int:
    return len(text.encode('utf-8'))


def classify_content(body, path, oversized, config):
    tokens = MarkdownIt('commonmark', {'html': True}).parse(body)
    headings = False
    visible = []
    has_code = any(t.type in {'fence', 'code_block'} for t in tokens)
    for token in tokens:
        if token.type == 'heading_open': headings = True
        elif token.type == 'heading_close': headings = False
        elif token.type == 'inline' and not headings:
            visible.extend(c.content for c in token.children or [] if c.type in {'text', 'code_inline'})
            has_code |= any(c.type == 'code_inline' for c in token.children or [])
    prose = ' '.join(visible).strip()
    reasons, relevance_reasons = [], []
    if not prose and not has_code:
        reasons.append('heading_only' if any(t.type == 'heading_open' for t in tokens) else 'non_substantive')
    relevance = 'technical_or_unknown'
    if config.relevance_enabled:
        if prose.casefold() in {'previous', 'next', 'back to top', 'edit this page', 'table of contents'}:
            relevance, relevance_reasons = 'navigation', ['standalone_navigation_label']
        elif (any(re.fullmatch(r'(?:(?:gold|silver|bronze|keystone)\s+)?sponsors?', p.strip(), re.I) for p in path)
              and not has_code):
            relevance, relevance_reasons = 'sponsorship', ['explicit_sponsorship_section_without_code']
        elif (re.search(r'\b(?:conference|conf\s*[\u2019\x27]?\d{2,4})\b', prose, re.I)
              and re.search(r'learn more|register|tickets', prose, re.I) and not has_code):
            relevance, relevance_reasons = 'promotion', ['event_promotion_with_call_to_action']
        if relevance_reasons and config.exclude_obvious_nontechnical:
            reasons.append('nontechnical_' + relevance)
    if oversized:
        reasons.append('oversized_block_requires_budget_review')
    return dict(extraction_eligible=not reasons, eligibility_reasons=reasons,
                content_relevance=relevance, relevance_reasons=relevance_reasons)


class SectionChunker:
    def __init__(self, config: ChunkingConfig | None = None):
        self.config = config or ChunkingConfig()

    def chunk(self, document, *, project_id: str) -> list[SectionChunk]:
        data = document.model_dump() if hasattr(document, 'model_dump') else deepcopy(dict(document))
        markdown = data['markdown']
        if not markdown.strip():
            return []
        document_id = data.get('document_id') or stable_id('doc', data['url'])
        parser = MarkdownIt('commonmark', {'html': True}).enable('table')
        tokens = parser.parse(markdown)
        lines = re.findall(r'[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+$', markdown)
        offsets = [0]
        for line in lines:
            offsets.append(offsets[-1] + len(line))
        headings = []
        protected = []
        boundaries = {0, len(markdown)}
        for index, token in enumerate(tokens):
            if token.map is None:
                continue
            start, end = (offsets[n] for n in token.map)
            if token.type in {'fence', 'code_block', 'html_block'}:
                protected.append((start, end, token.type))
            if token.level == 0:
                boundaries.update((start, end))
            if token.type == 'heading_open' and token.level == 0:
                headings.append((start, int(token.tag[1:]), tokens[index + 1].content))
        # Never put a boundary inside code, including code nested in lists.
        boundaries = sorted(n for n in boundaries if not any(a < n < b for a, b, _ in protected))
        sections, path = [], []
        previous = 0
        for start, level, title in headings:
            if start > previous:
                sections.append((previous, start, list(path)))
            path = [(lev, label) for lev, label in path if lev < level] + [(level, title)]
            previous = start
        sections.append((previous, len(markdown), list(path)))
        result = []
        for section_start, section_end, heading_path in sections:
            cuts = sorted({section_start, section_end, *(n for n in boundaries if section_start < n < section_end)})
            units = []
            for a, b in zip(cuts, cuts[1:]):
                cursor = a
                while count_tokens(markdown[cursor:b]) > self.config.max_tokens:
                    # A protected block remains intact, even if it exceeds budget.
                    block = next(((s, e, kind) for s, e, kind in protected if s <= cursor < e), None)
                    if block:
                        units.append((cursor, block[1], 'oversized_' + block[2]))
                        cursor = block[1]
                        continue
                    next_block = min([s for s, _, _ in protected if cursor < s < b] or [b])
                    limit = cursor
                    budget = 0
                    while limit < next_block and budget + count_tokens(markdown[limit]) <= self.config.max_tokens:
                        budget += count_tokens(markdown[limit])
                        limit += 1
                    preferred = max(markdown.rfind('\n', cursor, limit), markdown.rfind(' ', cursor, limit))
                    if preferred > cursor + (limit - cursor) // 2:
                        limit = preferred + 1
                    units.append((cursor, limit, 'split_large_block'))
                    cursor = limit
                if cursor < b:
                    units.append((cursor, b, None))
            packed = []
            for a, b, warning in units:
                if packed and not warning and not packed[-1][2] and count_tokens(markdown[packed[-1][0]:b]) <= self.config.max_tokens:
                    packed[-1] = (packed[-1][0], b, None)
                else:
                    packed.append((a, b, warning))
            previous_body = ''
            for a, b, warning in packed:
                body = markdown[a:b]
                if not body.strip():
                    # Source whitespace is not knowledge and does not become a chunk.
                    continue
                prefix = ''
                # Overlap only complete trailing paragraphs and never partial code.
                if previous_body and not warning and self.config.overlap_tokens:
                    tail = previous_body.rstrip('\r\n').rsplit('\n\n', 1)[-1]
                    if (tail.strip() and count_tokens(tail) <= self.config.overlap_tokens
                            and not any(s < a and e > a - len(tail) for s, e, _ in protected)
                            and count_tokens(tail + '\n\n' + body) <= self.config.max_tokens):
                        prefix = tail + '\n\n'
                text = prefix + body
                labels = [label for _, label in heading_path]
                oversized = count_tokens(text) > self.config.max_tokens
                result.append(SectionChunk(
                    project_id=project_id, document_id=document_id,
                    chunk_id=stable_id('chunk', project_id, document_id, str(a), str(b), text,
                                       str(self.config.max_tokens), str(self.config.overlap_tokens)),
                    url=data['url'], text=text, topic=' / '.join([data.get('title', ''), *labels]).strip(' /'),
                    document_title=data.get('title', ''), byte_count=count_tokens(text),
                    section_title=labels[-1] if labels else data.get('title', ''), heading_path=labels,
                    metadata=deepcopy(data.get('metadata', {})), start_char=a, end_char=b,
                    overlap_prefix=prefix, token_count=count_tokens(text),
                    oversized_reason=warning if oversized else None,
                    context_warnings=([warning] if warning == 'split_large_block' else []) +
                    (['cross_section_context_not_repeated'] if section_start > 0 else []),
                    **classify_content(body, labels, oversized, self.config),
                ))
                previous_body = body
        return result
