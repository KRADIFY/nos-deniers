"""Use dedicated RAP programme opening pages, never references in prose."""
import re


def programme_context(text):
    result = {}
    current, label, opening_page = '', '', None
    for number, page in enumerate(text.split('\f'), 1):
        match = re.search(r'^\s*PROGRAMME[ \t]+(\d{3})[ \t]*(?:\r?\n|$)', page, re.M)
        if match and len(page.strip()) < 800:
            current = match.group(1)
            label = ' '.join(page[match.end():].strip().split())
            opening_page = number
        result[number] = dict(program=current, label=label, opening_page=opening_page)
    return result
