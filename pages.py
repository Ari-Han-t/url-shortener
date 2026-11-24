"""Small server-rendered HTML pages in hop's style: short-link errors and the OAuth sign-in/consent screens."""
from typing import Optional

from fastapi.responses import HTMLResponse

_LOGO = """<svg width="40" height="40" viewBox="0 0 32 32" fill="none" aria-hidden="true">
<rect width="32" height="32" rx="8" fill="var(--accent)"/>
<circle cx="8.5" cy="21" r="3" fill="var(--accent-fg)"/>
<path d="M8.5 21C8.5 8 23.5 8 23.5 21" stroke="var(--accent-fg)" stroke-width="2.6" stroke-linecap="round"/>
<path d="M20 17.8l3.5 3.4 3.5-3.4" stroke="var(--accent-fg)" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>
</svg>"""

_CSS = """
:root{--bg:#fafaf9;--surface:#fff;--text:#1c1917;--muted:#625d58;--accent:#0b7a5a;--accent-hover:#09664b;--accent-fg:#fff;--line:#e4e2df;--danger:#b42318;color-scheme:light dark}
@media (prefers-color-scheme:dark){:root{--bg:#0d0f0e;--surface:#151816;--text:#ebeeec;--muted:#99a29d;--accent:#3ecf9e;--accent-hover:#5fdcb2;--accent-fg:#06241a;--line:#272d2a;--danger:#f87171}}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;padding:24px;text-align:center;background:var(--bg);color:var(--text);font:16px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif}
h1{margin:8px 0 0;font-size:22px;font-weight:600;letter-spacing:-.01em}
p{margin:0;max-width:30rem;color:var(--muted)}
a{color:var(--text)}
a.home{margin-top:8px;font-weight:500;text-underline-offset:3px}
a:focus-visible,button:focus-visible,input:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.card{width:100%;max-width:26rem;margin-top:8px;padding:20px;text-align:left;background:var(--surface);border:1px solid var(--line);border-radius:10px}
.card p{max-width:none}
label{display:block;margin:0 0 6px;font-size:14px;font-weight:500}
input[type=text],input[type=password]{display:block;width:100%;height:40px;margin-bottom:14px;padding:0 12px;font:inherit;font-size:14px;color:var(--text);background:var(--surface);border:1px solid var(--line);border-radius:6px}
ul.perms{margin:12px 0;padding-left:20px;color:var(--text);font-size:14px}
ul.perms li{margin:4px 0}
.row{display:flex;gap:8px;margin-top:16px}
button{flex:1;height:40px;font:inherit;font-size:14px;font-weight:500;border-radius:6px;border:1px solid var(--line);background:var(--surface);color:var(--text)}
button.primary{background:var(--accent);border-color:var(--accent);color:var(--accent-fg)}
button.primary:hover{background:var(--accent-hover)}
.err{min-height:20px;margin:0 0 8px;font-size:14px;color:var(--danger)}
.small{font-size:13px}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;word-break:break-all}
"""


def render_page(title: str, body_html: str, status_code: int = 200, headers: Optional[dict] = None) -> HTMLResponse:
    """`title` and `body_html` must already be safe HTML (escape any user-supplied text first)."""
    html = (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="robots" content="noindex">\n'
        f"<title>{title} - hop</title>\n<style>{_CSS}</style>\n</head>\n<body>\n{_LOGO}\n{body_html}\n</body>\n</html>\n"
    )
    h = {"Cache-Control": "no-store", **(headers or {})}
    return HTMLResponse(html, status_code=status_code, headers=h)


def status_page(status_code: int, title: str, message: str) -> HTMLResponse:
    # Titles and messages are fixed strings; nothing from the request is echoed.
    return render_page(
        title,
        f'<h1>{title}</h1>\n<p>{message}</p>\n<a class="home" href="/">Go to hop</a>',
        status_code,
        headers={"Cache-Control": "public, max-age=60"},
    )


def expired_page() -> HTMLResponse:
    return status_page(410, "This link has expired", "The person who created it set an expiry date, and that date has passed.")


def not_found_page() -> HTMLResponse:
    return status_page(404, "Link not found", "There is no link with this ID. Check the address and try again.")
