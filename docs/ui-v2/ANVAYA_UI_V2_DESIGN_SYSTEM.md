# Implemented workspace design system

Implementation: `workspace_base.html`, `static/css/workspace_v2.css`, `workspace_sources.css`, `static/js/workspace_v2.js`. Every new rule is scoped beneath `.workspace-v2`; only templates extending the new parent opt in. No application runtime/framework or network font was added.

| Role | Token / convention |
|---|---|
| Canvas / surface / raised | `--ws-canvas: #0c1117`, `--ws-surface: #131c25`, `--ws-raised: #192530` |
| Main / secondary text | `--ws-ink: #edf2f5`, `--ws-muted: #a5b1bf` |
| Accent / dividing line | `--ws-accent: #71ddd0`, `--ws-line: #2b3744` |
| Success / warning / error | Existing status semantics retained; warning notice left border #e2b879; error messaging remains explicit |
| Spacing | 4/8/12/16/20/24/32/40px; reading padding scales 20–52px |
| Surfaces | 14px panels, 8–12px controls/list surfaces; one-pixel borders, no decorative glow |
| Type | Existing system font stack, 25–34px page titles, 18–23px section headings, 14–16px body, 11–13px metadata |
| Measure | Workspace max 1300px; reading target 72ch; wide/focus reading with surrounding controls retained |
| Layout | 1100/860/700/640/520px adaptations; shell breakpoint remains 860px |
| Controls | 44px primary buttons and inputs; restrained filled primary action, outlined secondary action |
| Focus | 2px teal outline with 4px offset, native links/buttons/disclosures, roving keyboard tabs |
| Motion | Only short interaction transitions; reduced-motion removes animations/transitions |
| Icons / brand | Existing ANVAYA wordmark/mark; small local text symbols; ASCII plus for create control |

Home prioritizes the actual academic brief, labels its suggestion provisional, and sends the student to a real planning workflow. It does not invent resume sessions or mastery. Notes source boundaries, version fields and explicit saves remain visible. Filters and metadata use native disclosures; current filter values keep their disclosure open. Long code and tables scroll inside their reading panes.

Focus mode is progressive: hidden controls are revealed only by JavaScript. Exit, Escape, breakpoint changes and navigation remain reversible. Study Tools stays in the reader toolbar; its default selected tab is reachable by keyboard with normal motion. No-JavaScript mobile navigation uses a native 12-destination disclosure. Body/source content is never placed in localStorage.

Contrast: main/secondary text and focus/accent colors are deliberately light on charcoal; these are WCAG AA-oriented choices, not a complete accessibility certification. Synthetic browser checks, code/keyboard review and the independent visual review cover the implemented flows. OS font availability, native screen readers and physical-device text scaling remain separate validation limits.
