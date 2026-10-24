"""Escaped Markdown with no imported links, images, HTML or SVG execution."""
import html
import re
import mistune
from markupsafe import Markup


class UnsupportedMath(ValueError):
    pass


# A deliberately small local notation translator, never a TeX/HTML interpreter.
_MATH_SYMBOLS = dict(zip(
    'alpha beta gamma delta epsilon theta lambda mu pi rho sigma tau phi psi omega Gamma Delta Theta Lambda Pi Sigma Phi Psi Omega'.split(),
    'α β γ δ ε θ λ μ π ρ σ τ φ ψ ω Γ Δ Θ Λ Π Σ Φ Ψ Ω'.split()))
_MATH_OPERATORS = {'times': '×', 'cdot': '·', 'div': '÷', 'pm': '±', 'le': '≤',
                   'leq': '≤', 'ge': '≥', 'geq': '≥', 'ne': '≠', 'neq': '≠', 'approx': '≈'}


def _mathml(source):
    if len(source) > 2048:
        raise UnsupportedMath()
    tokens = re.findall(r'\\[A-Za-z]+|(?:\d+(?:\.\d+)?)|[^\s]', source)
    if not tokens or len(tokens) > 256:
        raise UnsupportedMath()
    index = 0

    def tag(name, value):
        return '<' + name + '>' + html.escape(value) + '</' + name + '>'

    def group(depth):
        nonlocal index
        if index >= len(tokens) or tokens[index] != '{':
            raise UnsupportedMath()
        index += 1
        content = sequence(depth + 1, closing=True)
        return '<mrow>' + content + '</mrow>'

    def atom(depth):
        nonlocal index
        if depth > 16 or index >= len(tokens):
            raise UnsupportedMath()
        token = tokens[index]
        if token == '{':
            return group(depth)
        index += 1
        if token == r'\frac':
            return '<mfrac>' + group(depth) + group(depth) + '</mfrac>'
        if token == r'\sqrt':
            return '<msqrt>' + group(depth) + '</msqrt>'
        if token.startswith('\\'):
            command = token[1:]
            if command in _MATH_SYMBOLS:
                return tag('mi', _MATH_SYMBOLS[command])
            if command in _MATH_OPERATORS:
                return tag('mo', _MATH_OPERATORS[command])
            raise UnsupportedMath()
        if re.fullmatch(r'\d+(?:\.\d+)?', token):
            return tag('mn', token)
        if re.fullmatch(r'[A-Za-z]', token):
            return tag('mi', token)
        if token in '+−-=*/(),.[]<>|:!%×÷≤≥≠±':
            return tag('mo', token)
        raise UnsupportedMath()

    def sequence(depth, closing=False):
        nonlocal index
        if depth > 16:
            raise UnsupportedMath()
        output = []
        while index < len(tokens) and tokens[index] != '}':
            base = atom(depth)
            scripts = {}
            while index < len(tokens) and tokens[index] in ('_', '^'):
                kind = tokens[index]; index += 1
                if kind in scripts:
                    raise UnsupportedMath()
                scripts[kind] = atom(depth + 1)
            if len(scripts) == 2:
                base = '<msubsup>' + base + scripts['_'] + scripts['^'] + '</msubsup>'
            elif scripts:
                name = 'msub' if '_' in scripts else 'msup'
                base = '<' + name + '>' + base + next(iter(scripts.values())) + '</' + name + '>'
            output.append(base)
        if closing:
            if index >= len(tokens) or not output:
                raise UnsupportedMath()
            index += 1
        return ''.join(output)

    result = sequence(0)
    if index != len(tokens):
        raise UnsupportedMath()
    return result


def _local_math(md):
    def parse(inline, match, state):
        opening = match.group(0)
        closing = {r'\(': r'\)', r'\[': r'\]', '$$': '$$'}[opening]
        start = match.end()
        # Bounded lookahead also handles hostile or unclosed delimiters linearly.
        end = state.src.find(closing, start, start + 2050)
        valid_end = end >= 0
        if not valid_end:
            newline = state.src.find('\n', start, start + 2048)
            end = newline if newline >= 0 else min(len(state.src), start + 2048)
        source = state.src[start:end]
        state.append_token({'type': 'local_math', 'raw': source,
                            'attrs': {'opening': opening, 'closed': valid_end}})
        return end + len(closing) if valid_end else end

    def render(renderer, text, opening, closed):
        closing = {r'\(': r'\)', r'\[': r'\]', '$$': '$$'}[opening]
        try:
            if not closed:
                raise UnsupportedMath()
            content = _mathml(text)
        except UnsupportedMath:
            return '<span class="ls-math-review">' + html.escape(opening + text + (closing if closed else '')) + ' <strong>Math needs review</strong></span>'
        display = 'inline' if opening == r'\(' else 'block'
        return '<math xmlns="http://www.w3.org/1998/Math/MathML" class="ls-local-math" tabindex="0" display="' + display + '" aria-label="' + html.escape(text, quote=True) + '"><mrow>' + content + '</mrow></math>'

    md.inline.register('local_math', r'\\\(|\\\[', parse, before='escape')
    # Separate the dollar trigger so Mistune's fast text scanner recognizes it.
    md.inline.register('local_math_display', r'\$\$', parse, before='escape')
    md.renderer.register('local_math', render)


class LocalRenderer(mistune.HTMLRenderer):
    def __init__(self, *args, anchor_prefix=None, section_targets=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.anchor_prefix=anchor_prefix
        self.heading_index=0
        self.section_targets = section_targets or {}

    def heading(self, text, level, **attrs):
        self.heading_index+=1
        anchor=(' id="'+html.escape(str(self.anchor_prefix),quote=True)+'-heading-'+str(self.heading_index)+'"') if self.anchor_prefix else ''
        return f'<h{level}{anchor}>{text}</h{level}>\n'

    def link(self, text, url, title=None):
        # The target map is produced by Flask from validated section identities.
        # Author-provided paths, URLs and arbitrary fragments remain inert.
        target = self.section_targets.get(url[1:]) if url.startswith('#') else None
        if target:
            return '<a href="' + html.escape(target,quote=True) + '">' + text + '</a>'
        return text

    def image(self, text, url, title=None):
        return '<span class="ls-media-alt">' + html.escape(text) + '</span>'


def markdown(text, anchor_prefix=None, *, section_targets=None):
    from mistune.plugins.table import render_table
    renderer = LocalRenderer(escape=True, anchor_prefix=anchor_prefix, section_targets=section_targets)
    render = mistune.create_markdown(renderer=renderer, plugins=['table', _local_math])
    renderer.register('table', lambda r, body: '<div class="ls-table-scroll" role="region" tabindex="0" aria-label="Authored comparison table">' + render_table(r, body) + '</div>')
    return Markup(render(str(text)))


def inline_markdown(text):
    """Escaped authored phrasing, including local math, without paragraph wrappers."""
    renderer = LocalRenderer(escape=True)
    render = mistune.create_markdown(renderer=renderer, plugins=[_local_math])
    state = render.block.state_cls()
    return Markup(renderer.render_tokens(render.inline(str(text), state.env), state))


def trusted_graph(block):
    """Accessible relational rendering from validated data; no imported SVG."""
    from .content_blocks import validate_extension
    validate_extension(block)
    if block['kind'] != 'graph':
        raise ValueError('Expected graph.')
    labels = {node['id']: node['label'] for node in block['nodes']}
    relationships = ''.join('<li><strong>' + html.escape(labels[e['from']]) + '</strong> <span>' + html.escape(e['label']) + '</span> → <strong>' + html.escape(labels[e['to']]) + '</strong></li>' for e in block['edges'])
    # Locally generated fixed lanes keep edges outside node interiors.
    import textwrap
    wrapped={node['id']:textwrap.wrap(node['label'],40) for node in block['nodes']}
    positions={};heights={};cursor=38
    for node in block['nodes']:
        node_height=max(64,15*len(wrapped[node['id']])+24)
        heights[node['id']]=node_height
        positions[node['id']]=(190,cursor+node_height/2)
        cursor+=node_height+46
    height=cursor+160
    lines=[]
    for index, edge in enumerate(block['edges']):
        y1=positions[edge['from']][1]; y2=positions[edge['to']][1]
        lane=390 + 130*index
        lines.append('<path d="M 350 ' + str(y1) + ' H ' + str(lane) + ' V ' + str(y2) + ' H 350" fill="none" stroke="currentColor" stroke-width="2"/>')
        lines.append(f'<polygon points="350,{y2:g} 360,{y2-5:g} 360,{y2+5:g}" fill="currentColor"/>')
        for offset, line in enumerate(textwrap.wrap(edge['label'], 18)):
            lines.append('<text x="' + str(lane+5) + '" y="' + str((y1+y2)//2 + offset*15) + '" fill="currentColor" font-size="12">' + html.escape(line) + '</text>')
    nodes=[]
    for node_id, (x,y) in positions.items():
        label_lines=wrapped[node_id]
        label=''.join('<tspan x="190" dy="' + ('0' if index==0 else '15') + '">' + html.escape(line) + '</tspan>' for index,line in enumerate(label_lines))
        node_height=heights[node_id]
        nodes.append('<g><rect x="30" y="' + str(y-node_height/2) + '" width="320" height="'+str(node_height)+'" rx="8" fill="none" stroke="currentColor"/><text x="190" y="' + str(y-7.5*(len(label_lines)-1)) + '" text-anchor="middle" fill="currentColor" font-size="12">' + label + '</text></g>')
    width=600 + 130*max(0,len(block['edges'])-1)
    svg='<p class="ls-text-alt">Scroll the diagram horizontally; the complete relationship list follows.</p><div class="ls-table-scroll" role="region" tabindex="0" aria-label="Source-linked relationship diagram"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + str(width) + ' ' + str(height) + '" width="' + str(width) + '" height="' + str(height) + '" aria-hidden="true" focusable="false">' + ''.join(lines+nodes) + '</svg></div>'
    return Markup('<figure class="ls-relationship-graph"><figcaption>' + html.escape(block['alt']) + '</figcaption>' + svg + '<ul aria-label="Represented relationships">' + relationships + '</ul></figure>')



def trusted_activity(block, widget_id):
    """Ungraded response/reveal loop; no form action or grading keys."""
    from .content_blocks import validate_extension
    from .validation import identity
    validate_extension(block); identity(widget_id)
    if block['kind'] != 'activity':
        raise ValueError('Expected activity.')
    choices=''.join('<option value="' + html.escape(c['id']) + '">' + html.escape(c['label']) + '</option>' for c in block['choices'])
    feedback=''.join('<dt>' + html.escape(c['label']) + '</dt><dd>' + html.escape(c['detail']) + '</dd>' for c in block['choices'])
    return Markup('<section class="ls-trusted-activity" data-widget="' + html.escape(block['widget']) + '"><p>' + html.escape(block['prompt']) + '</p><p>Ungraded activity · response is not a correctness score.</p><label for="' + widget_id + '-choice">Choose a perspective</label><select required id="' + widget_id + '-choice"><option value="">Choose before revealing</option>' + choices + '</select><label for="' + widget_id + '-response">Your prediction or comparison</label><textarea required id="' + widget_id + '-response" maxlength="3000"></textarea><details><summary>Compare your response with the authored explanation</summary><dl>' + feedback + '</dl><p>' + html.escape(block['feedback']) + '</p></details></section>')


def authored_headings(text):
    """Build navigation from actual Markdown AST headings, never from raw code lines."""
    ast=mistune.create_markdown(renderer='ast')(str(text));headings=[]
    def inline(tokens):
        return ''.join(str(token.get('raw',''))+inline(token.get('children',[])) for token in tokens)
    def visit(tokens):
        for token in tokens:
            if token['type']=='heading':
                headings.append({'index':len(headings)+1,'level':token['attrs']['level'],'label':inline(token.get('children',[]))})
            elif 'children' in token:visit(token['children'])
    visit(ast)
    return headings
