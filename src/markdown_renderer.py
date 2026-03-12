
import re

class MarkdownRenderer:
    """
    Shared Markdown → HTML converter used throughout the application.
    Call to_styled_html() for a complete dark-themed HTML document, or
    to_html() for an unstyled HTML fragment.
    """

    _font_size = 10

    @classmethod
    def style(cls):
        return (
            f"font-family:sans-serif; font-size:{cls._font_size}pt; "
            "background:#1e1e1e; color:#dddddd; padding:6px;"
        )

    @classmethod
    def set_font_size(cls, size):
        cls._font_size = size

    @staticmethod
    def _inline_md(text):
        """Apply inline markdown and pass through allowed HTML tags."""
        # Normalise <br> variants
        text = re.sub(r'<br\s*/?>', '<br/>', text, flags=re.IGNORECASE)
        # Images  ![alt](src)
        text = re.sub(
            r'!\[([^\]]*)\]\(([^)]*)\)',
            r'<img alt="\1" src="\2" style="max-width:100%"/>',
            text,
        )
        # Links  [label](url)
        text = re.sub(r'\[([^\]]+)\]\(([^)]*)\)', r'<a href="\2">\1</a>', text)
        # Bold  **text**
        text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
        # Underline  __text__
        text = re.sub(r'__(.+?)__', r'<u>\1</u>', text)
        # Italic  *text*  (not part of **)
        text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<i>\1</i>', text)
        return text

    @classmethod
    def to_html(cls, text):
        """Convert a subset of Markdown + basic HTML tags to an HTML fragment.
        Literal <div> block elements embedded in the text are passed through
        unchanged so that command-result boxes from AIPromptBar survive intact."""
        lines = text.split('\n')
        out = []
        in_ul = False

        for line in lines:
            # Horizontal rule: 3+ identical chars (-, *, _) optionally separated by spaces
            if re.match(r'^\s*([-*_])\s*(?:\1\s*){2,}\s*$', line):
                if in_ul:
                    out.append('</ul>'); in_ul = False
                out.append('<hr/>')
                continue

            # Headers H1–H4
            m = re.match(r'^(#{1,4})\s+(.*)', line)
            if m:
                if in_ul:
                    out.append('</ul>'); in_ul = False
                lvl = len(m.group(1))
                out.append(f'<h{lvl}>{cls._inline_md(m.group(2))}</h{lvl}>')
                continue

            # Bullet list item (-, *, + followed by whitespace)
            m = re.match(r'^\s*[-*+]\s+(.*)', line)
            if m:
                if not in_ul:
                    out.append('<ul>'); in_ul = True
                out.append(f'<li>{cls._inline_md(m.group(1))}</li>')
                continue

            # Any non-list line closes an open list
            if in_ul:
                out.append('</ul>'); in_ul = False

            # Empty line - blank spacer
            if not line.strip():
                out.append('<p style="margin:0">&nbsp;</p>')
                continue

            # Pass-through existing HTML block elements (<p>, <div>, etc.)
            stripped = line.strip()
            if re.match(r'^<(?:/?p|div)[^>]*>', stripped, re.IGNORECASE):
                out.append(line)
                continue

            # Normal paragraph line
            out.append(f'<p style="margin:2px 0">{cls._inline_md(line)}</p>')

        if in_ul:
            out.append('</ul>')

        return '\n'.join(out)

    @classmethod
    def to_styled_html(cls, text):
        """Return a full HTML document with dark-theme styling."""
        return (
            f"<html><body style='{cls.style()}'>"
            + cls.to_html(text)
            + "</body></html>"
        )
