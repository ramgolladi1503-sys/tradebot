TOKENS = {
    "colors": {
        "bg": "#0b0f14",
        "surface": "#0f172a",
        "surface_alt": "#111827",
        "border": "rgba(94,234,212,0.25)",
        "accent": "#5eead4",
        "text": "#e6f3ff",
        "muted": "#9fb6cf",
        "success": "#22c55e",
        "warn": "#f59e0b",
        "error": "#ef4444",
    },
    "spacing": {
        "xs": "4px",
        "sm": "8px",
        "md": "12px",
        "lg": "16px",
        "xl": "24px",
        "2xl": "32px",
    },
    "radius": {
        "sm": "6px",
        "md": "10px",
        "lg": "14px",
    },
    "font": {
        "body": "Manrope, sans-serif",
        "heading": "Fraunces, serif",
        "size_sm": "0.85rem",
        "size_md": "0.95rem",
        "size_lg": "1.1rem",
        "size_xl": "1.4rem",
    },
    "max_width": "1200px",
}


def css(tokens: dict | None = None) -> str:
    t = tokens or TOKENS
    c = t["colors"]
    s = t["spacing"]
    r = t["radius"]
    f = t["font"]
    return f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Fraunces:wght@400;600;700&family=Manrope:wght@400;500;600&display=swap');
    :root {{
      --bg: {c['bg']};
      --surface: {c['surface']};
      --surface-alt: {c['surface_alt']};
      --border: {c['border']};
      --accent: {c['accent']};
      --text: {c['text']};
      --muted: {c['muted']};
      --success: {c['success']};
      --warn: {c['warn']};
      --error: {c['error']};
      --space-xs: {s['xs']};
      --space-sm: {s['sm']};
      --space-md: {s['md']};
      --space-lg: {s['lg']};
      --space-xl: {s['xl']};
      --radius-sm: {r['sm']};
      --radius-md: {r['md']};
      --radius-lg: {r['lg']};
      --font-body: {f['body']};
      --font-heading: {f['heading']};
      --font-sm: {f['size_sm']};
      --font-md: {f['size_md']};
      --font-lg: {f['size_lg']};
      --font-xl: {f['size_xl']};
      --max-width: {t['max_width']};
    }}
    html, body, [class*="css"] {{ font-family: var(--font-body); color: var(--text); background: var(--bg); }}
    h1, h2, h3, h4, h5 {{ font-family: var(--font-heading); letter-spacing: 0.2px; }}
    .block-container {{ padding-top: 2.6rem !important; padding-bottom: 2rem !important; }}
    .app-shell-header {{
      background: linear-gradient(135deg, #0b1220 0%, #0a0f18 100%);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      padding: var(--space-md) var(--space-lg);
      margin-bottom: var(--space-lg);
      box-shadow: 0 10px 28px rgba(2,6,23,0.35);
    }}
    .app-shell-title {{ font-size: var(--font-xl); font-weight: 800; }}
    .breadcrumbs {{ color: var(--muted); font-size: var(--font-sm); margin-top: 2px; }}
    .app-container {{ max-width: var(--max-width); margin: 0 auto; }}
    .section-title {{
      font-size: var(--font-lg);
      font-weight: 600;
      padding: 6px 0;
      border-bottom: 1px solid var(--border);
      margin-top: var(--space-md);
      margin-bottom: var(--space-md);
    }}
    .card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      padding: var(--space-md);
      margin-bottom: var(--space-md);
    }}
    .badge {{ display: inline-flex; padding: 4px 10px; border-radius: 999px; font-weight: 700; font-size: var(--font-sm); }}
    .badge.success {{ background: rgba(34,197,94,0.2); color: var(--success); }}
    .badge.warn {{ background: rgba(245,158,11,0.2); color: var(--warn); }}
    .badge.error {{ background: rgba(239,68,68,0.2); color: var(--error); }}
    .empty-state {{ padding: var(--space-md); border: 1px dashed var(--border); border-radius: var(--radius-md); color: var(--text); }}
    .banner {{ padding: 10px 12px; border-radius: var(--radius-sm); margin: 6px 0; border: 1px solid var(--border); }}
    .banner.error {{ background: rgba(239,68,68,0.15); border-color: rgba(239,68,68,0.45); }}
    .banner.warn {{ background: rgba(245,158,11,0.15); border-color: rgba(245,158,11,0.45); }}
    .banner.success {{ background: rgba(34,197,94,0.15); border-color: rgba(34,197,94,0.45); }}
    .skeleton {{
      height: 14px; margin: 8px 0; border-radius: var(--radius-sm);
      background: linear-gradient(90deg, rgba(15,23,42,0.4), rgba(94,234,212,0.15), rgba(15,23,42,0.4));
      background-size: 200% 100%; animation: shimmer 1.4s infinite;
    }}
    @keyframes shimmer {{ 0% {{ background-position: 0% 0; }} 100% {{ background-position: 200% 0; }} }}
    .rt-table-wrap {{ max-height: 420px; overflow: auto; border: 1px solid var(--border); border-radius: var(--radius-md); }}
    .rt-table {{ width: 100%; border-collapse: collapse; font-size: var(--font-sm); }}
    .rt-table thead th {{
      position: sticky; top: 0; background: var(--bg); color: var(--text); text-align: left;
      padding: 8px 10px; border-bottom: 1px solid var(--border); z-index: 2;
    }}
    .rt-table tbody td {{ padding: 6px 10px; border-bottom: 1px solid rgba(94,234,212,0.12); }}
    .rt-table tbody tr:hover {{ background: rgba(94,234,212,0.08); }}
    </style>
    """
