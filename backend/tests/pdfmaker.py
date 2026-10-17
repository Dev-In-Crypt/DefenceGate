"""A tiny PDF writer for tests: text at fixed positions, nothing else. Enough for pypdf to read
back in both extraction modes, so the factsheet reader is tested on a real PDF without shipping
a real one."""

from __future__ import annotations


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(pages: list[list[tuple[int, int, str]]]) -> bytes:
    """pages: for each page a list of (x, y, text), y counted from the bottom of an A4 page."""
    objs: list[bytes] = []
    n_pages = len(pages)
    # 1 catalog, 2 pages, 3 font, then (page, content) pairs
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(n_pages))
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode())
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for i, items in enumerate(pages):
        content = "\n".join(f"BT /F1 10 Tf {x} {y} Td ({_esc(t)}) Tj ET" for x, y, t in items)
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                    f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2 * i} 0 R >>".encode())
        objs.append(f"<< /Length {len(content)} >>\nstream\n{content}\nendstream".encode())
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n").encode()
    return bytes(out)


MEMBERS = [
    ("(Coordinator) TALGEN CYBERSECURITY OU", "Estonia"),
    ("ALITER TECHNOLOGIES, AS", "Slovakia"),
    ("FUNDACION CENTRO TECNOLOXICO DE", "Spain"),
    ("TELECOMUNICACIONS DE GALICIA", ""),
    ("SAFRAN ELECTRONICS & DEFENSE", "France"),
]
SECRET = "A SECRET TECHNICAL DESCRIPTION OF THE SYSTEM"


def factsheet_pdf(acronym: str = "STRATUS", title: str = "Swarm Threat Resilience",
                  members: list[tuple[str, str]] | None = None, description: str = SECRET) -> bytes:
    """A factsheet shaped like the 2025 ones: project page with a description, consortium table.
    A member with an empty country continues the name above it (a wrapped name)."""
    members = MEMBERS if members is None else members
    page1 = [(50, 800, acronym), (50, 785, f"{acronym} - {title}"),
             (50, 750, "SELECTED PROJECTS EUROPEAN DEFENCE FUND (EDF) 2025"),
             (50, 720, "CALL TITLE:"), (260, 720, "Technological challenge research actions"),
             (50, 700, "DURATION OF THE PROJECT:"), (260, 700, "36 Months"),
             (50, 680, "ESTIMATED TOTAL COST:"), (260, 680, "EUR 19,946,187.63"),
             (50, 660, "MAXIMUM EU CONTRIBUTION :"), (260, 660, "EUR 19,946,186.41"),
             (50, 630, "SHORT DESCRIPTION OF THE PROJECT:"), (50, 610, description)]
    page2 = [(50, 800, "SELECTED PROJECTS EUROPEAN DEFENCE FUND (EDF) 2025"),
             (50, 760, "NAME"), (400, 760, "COUNTRY")]
    # Like the real files, the names are stored as one block and the countries as another, so the
    # plain text reads a wrapped name whole and the layout text reads a row.
    y, names, countries = 720, [], []
    for i, (name, country) in enumerate(members):
        names.append((50, y, name))
        if country:
            countries.append((400, y, country))
        wraps = i + 1 < len(members) and not members[i + 1][1]
        y -= 12 if wraps else 30
    page2 += names + countries
    return make_pdf([page1, page2])
