import pytest
from knowledge.chunking import ChunkingConfig, SectionChunker, count_tokens
from knowledge.models import SourceChunk


def document(text):
    return dict(url='https://example.com/docs', document_id='doc-1', title='Docs',
                markdown=text, metadata={'depth': 1, 'custom': ['keep']})


def test_hierarchy_metadata_stability_and_source_contract():
    source = document('# Root\n\nIntro\n\n## Child\n\nBody\n\n###### Deep\n\nMore')
    chunker = SectionChunker()
    chunks = chunker.chunk(source, project_id='p')
    assert [c.heading_path for c in chunks] == [['Root'], ['Root','Child'], ['Root','Child','Deep']]
    assert all(c.metadata == source['metadata'] and c.document_id == 'doc-1' for c in chunks)
    assert chunks == chunker.chunk(source, project_id='p')
    assert isinstance(chunks[0].as_source_chunk(), SourceChunk)
    chunks[0].metadata['custom'].append('changed')
    assert source['metadata']['custom'] == ['keep']


@pytest.mark.parametrize('text', ['word ' * 200, '- item\n' * 100, '中文😀' * 100])
def test_limits_and_full_coverage(text):
    chunks = SectionChunker(ChunkingConfig(128, 16)).chunk(document(text), project_id='p')
    assert all(c.token_count <= 128 and c.text.strip() for c in chunks)
    assert ''.join(c.text[len(c.overlap_prefix):] for c in chunks) == text


def test_code_is_atomic_and_oversized_is_explicit():
    code = '```python\n' + 'print(1)  \n' * 70 + '```\n'
    text = '# Code\n\nParagraph\n\n' + code + '\nAfter'
    chunks = SectionChunker(ChunkingConfig(128, 16)).chunk(document(text), project_id='p')
    assert any(code in c.text and c.oversized_reason == 'oversized_fence' for c in chunks)
    assert ''.join(c.text[len(c.overlap_prefix):] for c in chunks).strip() == text.strip()


def test_empty_setext_lists_and_code_headings():
    chunker = SectionChunker()
    assert chunker.chunk(document(' \n'), project_id='p') == []
    text = 'Title\n=====\n\n- a\n- b\n\n```\n# not heading\n```'
    result = chunker.chunk(document(text), project_id='p')
    assert len(result) == 1 and result[0].heading_path == ['Title'] and result[0].text == text


def test_invalid_config():
    with pytest.raises(ValueError): ChunkingConfig(32,32)


def test_overlap_is_bounded_and_does_not_replace_source_content():
    text = 'a' * 70 + '\n\n' + 'b' * 20 + '\n\n' + 'c' * 100
    chunks = SectionChunker(ChunkingConfig(128,32)).chunk(document(text), project_id='p')
    assert any(c.overlap_prefix for c in chunks)
    assert all(c.token_count <= 128 for c in chunks)
    assert ''.join(c.text[len(c.overlap_prefix):] for c in chunks) == text


def test_heading_only_and_image_only_are_retained_but_ineligible():
    chunks = SectionChunker().chunk(document('# Root\n\n## Child\n\n![logo](https://example.com/logo.png)'), project_id='p')
    assert len(chunks) == 2
    assert all(not c.extraction_eligible for c in chunks)
    assert 'heading_only' in chunks[0].eligibility_reasons


def test_context_contains_document_title_path_and_original_content():
    c = SectionChunker().chunk(document('# API\n\nFastAPI uses Pydantic.'), project_id='p')[0]
    assert c.extraction_context() == dict(document_title='Docs', heading_path=['API'],
                                         section_title='API', content=c.text)
    assert 'Docs' in c.as_source_chunk().topic
    assert c.extraction_eligible


def test_byte_configuration_and_unicode_counts_are_explicit():
    config = ChunkingConfig(max_bytes=128, overlap_bytes=16)
    assert config.max_tokens == config.max_bytes == 128
    c = SectionChunker(config).chunk(document('中文😀'), project_id='p')[0]
    assert c.byte_count == c.token_count == len('中文😀'.encode('utf-8'))
    assert c.tokenizer == 'utf8-byte-v1'


def test_relevance_can_be_disabled_and_code_is_retained():
    source = document('# Sponsors\n\n[Company](https://example.com)')
    flagged = SectionChunker().chunk(source, project_id='p')[0]
    assert not flagged.extraction_eligible and flagged.content_relevance == 'sponsorship'
    kept = SectionChunker(ChunkingConfig(relevance_enabled=False)).chunk(source, project_id='p')[0]
    assert kept.extraction_eligible and kept.chunk_id == flagged.chunk_id and kept.text == flagged.text
    review = SectionChunker(ChunkingConfig(exclude_obvious_nontechnical=False)).chunk(source, project_id='p')[0]
    assert review.extraction_eligible and review.relevance_reasons
    code = '# Sponsors\n\n```python\n# API example\nprint(1)\n```'
    c = SectionChunker().chunk(document(code), project_id='p')[0]
    assert c.extraction_eligible and c.text == code


def test_diagnostics_do_not_determine_eligibility():
    chunks = SectionChunker().chunk(document('# A\n\nParagraph.\n\n## B\n\nAnother paragraph.'), project_id='p')
    assert chunks[-1].context_warnings and chunks[-1].extraction_eligible
