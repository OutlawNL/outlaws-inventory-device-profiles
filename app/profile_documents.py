"""Generic, fail-closed document discovery and extraction for Device Profiles."""
from __future__ import annotations
import re
import unicodedata
from datetime import datetime
from io import BytesIO
from urllib.parse import urljoin, urlsplit, unquote

import pdfplumber
from bs4 import BeautifulSoup


def normalize(value):
    return ' '.join(unicodedata.normalize('NFKC', str(value)).replace('’', "'").split())


def discover(html, base_url, rule):
    """Select one link inside its own download row; never score unrelated links."""
    selector = rule.get('item_selector', 'li')
    titles = [normalize(x).casefold() for x in rule.get('title_contains', [])]
    required = [normalize(x).casefold() for x in rule.get('url_contains', [])]
    excluded = [normalize(x).casefold() for x in rule.get('url_excludes', [])]
    pattern = rule.get('url_pattern', '')
    if not titles:
        return ''
    candidates = set()
    for row in BeautifulSoup(html, 'html.parser').select(selector):
        # Containers that include several download rows are not a single item.
        if row.select(selector):
            continue
        visible = normalize(row.get_text(' ', strip=True)).casefold()
        if not any(title in visible for title in titles):
            continue
        for anchor in row.select('a[href]'):
            url = urljoin(base_url, anchor['href'])
            parts = urlsplit(url)
            low = normalize(unquote(url)).casefold()
            if parts.scheme != 'https' or not parts.path.lower().endswith('.pdf'):
                continue
            if not all(token in low for token in required) or any(token in low for token in excluded):
                continue
            if pattern and not re.search(pattern, url, re.I):
                continue
            candidates.add(url)
    return next(iter(candidates)) if len(candidates) == 1 else ''


def first_page_text(content, options=None):
    with pdfplumber.open(BytesIO(content)) as pdf:
        if not pdf.pages:
            return ''
        return pdf.pages[0].extract_text(**(options or {})) or ''


def _value(lines, labels):
    values = []
    for line in lines:
        for label in labels:
            prefix = normalize(label).rstrip(':').strip()
            match = re.match(re.escape(prefix) + r'\s*:\s*(.*)$', line, re.I)
            if match:
                values.append(match.group(1))
                break
    # Even duplicate labels can indicate overlapping release blocks.
    return values[0] if len(values) == 1 else ''


def extract(text, firmware):
    """Read only the first release on the first page, using declared labels."""
    result = {'latest': '', 'release_date': '', 'summary': '', 'error': ''}
    rules = firmware.get('extraction', {})
    validation = firmware.get('validation', {})
    if rules.get('scope') != 'first_release_first_page':
        result['error'] = 'Device Profile needs a supported release scope; update the catalog.'
        return result
    lines = [normalize(x) for x in text.splitlines() if normalize(x)]
    expected = [normalize(x).casefold() for x in validation.get('document_titles', [])]
    if not lines or not expected or lines[0].casefold() not in expected:
        result['error'] = 'Release Notes document title did not match the Device Profile.'
        return result
    section = rules.get('whats_new', {})
    starts = {normalize(x).casefold() for x in section.get('start_labels', [])}
    ends = {normalize(x).casefold() for x in section.get('end_labels', [])}
    start = next((i for i, x in enumerate(lines) if x.casefold() in starts), None)
    if start is None:
        result['error'] = 'Release Notes structure was not recognized.'
        return result
    header = lines[1:start]
    if any(x.casefold() in expected or x.casefold() in ends for x in header):
        result['error'] = 'The first release block was incomplete.'
        return result
    vr = rules.get('version', {})
    raw_version = _header_value(header, vr)
    match = re.fullmatch(vr.get('pattern', r'(?!)'), raw_version)
    if match:
        version = match.group(int(vr.get('group', 1)))
        if re.fullmatch(validation.get('version_pattern', r'(?!)'), version):
            result['latest'] = version
    dr = rules.get('release_date', {})
    raw_date = _header_value(header, dr)
    for fmt in dr.get('formats', []):
        try:
            result['release_date'] = datetime.strptime(raw_date, fmt).date().isoformat()
            break
        except ValueError:
            pass
    # Never continue into a second release if the first Notes terminator is absent.
    end = next((i for i in range(start + 1, len(lines)) if lines[i].casefold() in ends), None)
    if end is not None:
        body = lines[start + 1:end]
        boundary_labels = dr.get('labels', []) + vr.get('labels', [])
        crossed = any(any(x.casefold().startswith(normalize(label).casefold()) for label in boundary_labels) or x.casefold() in starts or x.casefold() in expected for x in body)
        if not crossed:
            bullets = []
            for line in body:
                if line.startswith(('•', '\uf06c', '\uf0b7', '●', '- ')):
                    bullets.append(line.lstrip('•\uf06c\uf0b7●- ').strip())
                elif bullets:
                    bullets[-1] += ' ' + line
                else:
                    bullets.append(line)
            result['summary'] = '\n'.join(bullets[:int(section.get('max_items', 10))])
    if not result['latest']:
        result['error'] = "Release Notes PDF was read, but the profile's firmware-version rule did not produce a valid value."
        result['summary'] = ''
    elif not result['release_date']:
        result['error'] = 'Release Notes date was missing, invalid or ambiguous.'
    return result


def _header_value(header, rule):
    """Optional explicit multiline layout pattern, confined to one release header."""
    pattern = rule.get('header_pattern')
    if pattern:
        matches = list(re.finditer(pattern, '\n'.join(header), re.M))
        return matches[0].group(1) if len(matches) == 1 else ''
    return _value(header, rule.get('labels', []))


def extract_pdf(content, firmware):
    rules = firmware.get('extraction', {})
    options = rules.get('pdf_text', {})
    if rules.get('scope') != 'first_release_for_target':
        return extract(first_page_text(content, options), firmware)
    # Skip only explicitly identified releases for another primary component.
    # An unreadable or malformed release must never expose an older known version.
    local = dict(firmware, extraction=dict(rules, scope='first_release_first_page'))
    invalid = {'latest': '', 'release_date': '', 'summary': '',
               'error': 'The first release for this component could not be identified safely.'}
    with pdfplumber.open(BytesIO(content)) as pdf:
        for page in pdf.pages[:min(int(rules.get('max_pages', 10)), 30)]:
            text = page.extract_text(**options) or ''
            lines = [normalize(x) for x in text.splitlines() if normalize(x)]
            titles = {normalize(x).casefold() for x in firmware['validation']['document_titles']}
            starts = {normalize(x).casefold() for x in rules['whats_new']['start_labels']}
            if not lines or lines[0].casefold() not in titles:
                return invalid
            start = next((i for i, line in enumerate(lines) if line.casefold() in starts), None)
            if start is None:
                return invalid
            header = lines[1:start]
            ends = {normalize(x).casefold() for x in rules['whats_new']['end_labels']}
            if any(line.casefold() in titles or line.casefold() in ends for line in header):
                return invalid
            def present(labels):
                return any(re.match(re.escape(normalize(label).rstrip(':').strip()) + r'\s*:', line, re.I)
                           for label in labels for line in header)
            if present(rules['version']['labels']):
                return extract(text, local)
            date = _header_value(header, rules['release_date'])
            date_ok = False
            for fmt in rules['release_date']['formats']:
                try:
                    datetime.strptime(date, fmt)
                    date_ok = True
                except ValueError:
                    pass
            if not date_ok or not present(rules.get('skip_when_labels', [])):
                return invalid
    return invalid


def extract_html(html, firmware):
    """Read a validated product header and its matching release-history item."""
    result = {'latest': '', 'release_date': '', 'summary': '', 'error': ''}
    rules = firmware['extraction']
    layout = rules['html']
    soup = BeautifulSoup(html, 'html.parser')
    def single(root, selector):
        found = root.select(selector)
        return found[0] if len(found) == 1 else None
    title = single(soup, layout['title_selector'])
    expected = {normalize(x).casefold() for x in firmware['validation']['document_titles']}
    header = single(soup, layout['header_selector'])
    if title is None or normalize(title.get_text(' ', strip=True)).casefold() not in expected or header is None:
        result['error'] = 'Firmware page product header did not match the Device Profile.'
        return result
    # Reuse the same date/version validation; synthetic section markers are local,
    # not read from untrusted page content and never used for summary extraction.
    local = dict(firmware, extraction=dict(rules, scope='first_release_first_page',
                 whats_new={'start_labels': ['__PROFILE_BODY__'], 'end_labels': ['__PROFILE_END__']}))
    text = title.get_text(' ', strip=True) + '\n' + header.get_text('\n', strip=True) + '\n__PROFILE_BODY__\n__PROFILE_END__'
    result = extract(text, local)
    if not result['latest']:
        return result
    matches = []
    for item in soup.select(layout['release_selector']):
        node = single(item, layout['release_version_selector'])
        if node is None:
            continue
        match = re.fullmatch(layout['release_version_pattern'], normalize(node.get_text(' ', strip=True)))
        if match and match.group(1) == result['latest']:
            matches.append(item)
    if len(matches) != 1:
        result['error'] = 'Release details were missing or ambiguous; version and date came from the product header.'
        return result
    points = [normalize(x.get_text(' ', strip=True)) for x in matches[0].select(layout['summary_selector'])]
    limit = min(int(rules.get('whats_new', {}).get('max_items', 10)), 10)
    result['summary'] = '\n'.join([x for x in points if x][:limit])[:20000]
    return result
