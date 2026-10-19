"""A country as a visitor writes it ("DE", "DEU", "Germany", "germany") to its ISO 3166-1 alpha-2 code.

The supplier filter stores alpha-2 codes; a person types whatever they know (UX audit M6, 19 October 2026:
`?country=Germany` and `?country=DEU` were a 404 page). The three-letter table is the one the TED connector
already uses (`normalise._ISO3_TO_2`); the English names below are the CLDR short names the browser shows,
plus the usual alternatives. A name is compared without case, accents and punctuation ("Côte d'Ivoire",
"cote divoire"). Nothing here guesses: a value that is none of the three forms is `None`.
"""
from __future__ import annotations

import re
import unicodedata

from .normalise import _ISO3_TO_2

# code|names (the first is the one shown; the others are alternatives people type)
_NAMES = """
AL|Albania;AT|Austria;BE|Belgium;BA|Bosnia and Herzegovina,Bosnia;BG|Bulgaria;BY|Belarus;CH|Switzerland;CY|Cyprus;
CZ|Czechia,Czech Republic;DE|Germany,Deutschland;DK|Denmark;EE|Estonia;ES|Spain,Espana;FI|Finland;FR|France;
GB|United Kingdom,UK,Great Britain,Britain,England;GR|Greece;HR|Croatia;HU|Hungary;IE|Ireland;IS|Iceland;IT|Italy,Italia;
LI|Liechtenstein;LT|Lithuania;LU|Luxembourg;LV|Latvia;MC|Monaco;MD|Moldova;ME|Montenegro;MK|North Macedonia,Macedonia;
MT|Malta;NL|Netherlands,The Netherlands,Holland;NO|Norway;PL|Poland,Polska;PT|Portugal;RO|Romania;RS|Serbia;
RU|Russia,Russian Federation;SE|Sweden;SI|Slovenia;SK|Slovakia,Slovak Republic;SM|San Marino;TR|Turkiye,Turkey;UA|Ukraine;
XK|Kosovo;EU|European Union;AD|Andorra;VA|Vatican City,Holy See;
AE|United Arab Emirates,UAE;AM|Armenia;AU|Australia;AZ|Azerbaijan;BD|Bangladesh;BR|Brazil;CA|Canada;CL|Chile;CN|China;
CO|Colombia;EG|Egypt;GE|Georgia;HK|Hong Kong;ID|Indonesia;IL|Israel;IN|India;IQ|Iraq;IR|Iran;JO|Jordan;JP|Japan;
KR|South Korea,Korea,Republic of Korea;KW|Kuwait;KZ|Kazakhstan;LB|Lebanon;MA|Morocco;MX|Mexico;MY|Malaysia;NG|Nigeria;
NZ|New Zealand;PH|Philippines;PK|Pakistan;QA|Qatar;SA|Saudi Arabia;SG|Singapore;TH|Thailand;TN|Tunisia;TW|Taiwan;
US|United States,USA,United States of America,America;UZ|Uzbekistan;VN|Vietnam;ZA|South Africa;DZ|Algeria;AR|Argentina;
SY|Syria;LY|Libya;KP|North Korea;KE|Kenya;GH|Ghana;ET|Ethiopia;BH|Bahrain;OM|Oman;PE|Peru;VE|Venezuela;UY|Uruguay;
CU|Cuba;LK|Sri Lanka;NP|Nepal;MM|Myanmar,Burma;KH|Cambodia;LA|Laos;MN|Mongolia;KG|Kyrgyzstan;TJ|Tajikistan;
TM|Turkmenistan;AF|Afghanistan;PS|Palestine;YE|Yemen;SD|Sudan;SN|Senegal;CI|Ivory Coast,Cote d Ivoire;CM|Cameroon;
TZ|Tanzania;UG|Uganda;AO|Angola;MZ|Mozambique;ZW|Zimbabwe;ZM|Zambia;BW|Botswana;NA|Namibia;MU|Mauritius
"""


def _key(text: str) -> str:
    """Lower case, no accents, "&" read as "and", every other mark dropped, words joined by one space."""
    s = unicodedata.normalize("NFKD", text.replace("&", " and ")).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s.lower()).split())


_BY_NAME: dict[str, str] = {}
for _row in _NAMES.replace("\n", "").split(";"):
    if not _row.strip():
        continue
    _code, _names = _row.strip().split("|")
    for _n in _names.split(","):
        _BY_NAME[_key(_n)] = _code


def to_iso2(value: str) -> str | None:
    """`DE`, `deu`, `Germany`, ` germany ` -> `DE`; a value that is none of the three forms -> `None`.

    Two letters are a code as written, so the filter keeps answering "no suppliers" for a code nobody holds (`ZZ`),
    as it did; only "UK", which is no ISO code, is read as the name it is (GB).
    """
    raw = (value or "").strip()
    code = raw.upper()
    if len(code) == 2 and code.isascii() and code.isalpha():
        return _BY_NAME.get(_key(raw)) or code
    return _ISO3_TO_2.get(code) or _BY_NAME.get(_key(raw))
