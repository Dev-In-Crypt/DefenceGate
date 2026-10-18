"""Organisations that are natural persons (WP-39, verify2-abuse N2).

CORDIS and the EDF factsheets publish every beneficiary under the name it is registered with. Sole
traders, freelance researchers and self-employed consultants are registered under their own name, so the
organisation directory, the profile pages and the partner lists showed a person with a PIC, a country and
an EU amount (3 of a random 300 of the 73,347 organisations on 18 October 2026, 1.0 %: "MIRABILE ANTONIO",
"CHONG TON SIN", "VAN DEN BERGH JOHANNA"). The sources state no legal form, so the rule is on the name.

The rule is on the side of hiding. A legal entity hidden by mistake is a gap in a directory; a person shown
with the money they received is a harm. It flags a name when

  - it has no legal form and no organisational word (university, council, foundation, a legal form in any of
    the languages the sources use) and is two to five words long, and at least one word is a given name of
    the list below ("TENNANT DAVID ROBIN", "Melina Bucher", "Gitte Wichmann-Hansen"); or
  - it carries a sole-proprietor form (PL "S.C.", DE "e.K.", RO "PFA", FR "EIRL") beside a given name
    ("WAMECO S.C. RYSZARD SZPADT, WOJCIECH GORNIKOWSKI"); or
  - it ends in a parenthesis that holds a person's name, the owner of a named business
    ("ARENDT BUSINESS CONSULTING (HANS-HENNING ARENDT)").

What it does not find: a person whose given name is not on the list (the list is western and central
European, with a few Greek, Turkish and Baltic names; Asian and African names are mostly missed), a name
written in a script other than Latin, and a business named for its owner that carries an organisational
word ("Mueller Bau"). The measured share and the hand check are in `docs/verification/product/wp39-selfcheck.md`.
`mark_individuals` stores the verdict and its reason on `organisation.individual_reason`; nothing is deleted:
the row, its participations and its aliases stay, the public read side does not show them.
"""

from __future__ import annotations

import logging
import re

import psycopg

from .awards import _CORPORATE, _SOLE_TRADER, _SOLE_TRADER_BY_COUNTRY, _words

log = logging.getLogger(__name__)

# Words that make a name an organisation although awards._CORPORATE does not list them: the vocabulary of
# research bodies, public bodies, associations and funds in the languages of the sources (taken from the
# commonest words of the 73,347 names; the legal forms and business words are in awards._CORPORATE).
_ORG_WORDS = frozenset("""
    stichting stiftelsen stiftung stiftelse fondazione fondation fundacion fundacao fundacja fundacio fundatia
    fund fonds foundation trust council counseil comune comuna commune kommune kommun kunta kaupunki
    municipality municipio municipiu gemeente dimos stadt city county region regione regio mesto miasto
    university universitat universitaet universitet universitesi universidad universidade universita universite
    universiteit univerzita universitatea universytet uniwersytet egyetem yliopisto hogeschool hochschule
    college school schule skola ecole escuela scuola academy akademie akademia accademia institut institute
    instituto istituto institutul instytut research recherche forschung onderzoek ricerca investigacion
    network netwerk reseau federation federatie federacion federazione foundation society societe societat
    sociedad societa selskab forening forbund verein vereniging association asociacion asociatia asociacija
    associazione associacao associacio stowarzyszenie sdruzeni sdruzenie union unie unione sindicato
    authority autoriteit agency agentschap agentur agencia agenzia amt office bureau ministry ministerie
    ministerium ministerio ministero
    museum muzeum musee museo library bibliotheca bibliotheek biblioteca bibliotek
    hospital hopital hopitaux spital ospedale ospedal nemocnice klinik clinic clinique klinika clinica klinikum
    lab labs laboratory laboratoire laboratorium laboratorio
    centre center centro centrum zentrum cent central centrale
    national nationale nazionale nacional nationaal
    european europeen europeo europese
    technology technologie technologies tecnologia technical technische tecnica technologii
    science sciences wissenschaft wetenschap scienze ciencias
    health sante gesundheit salud salute
    innovation innovatie innovazione
    cooperative coop cooperativa genossenschaft
    development developpement entwicklung
    forum alliance cluster consortium partnership partnerschap
    chamber kammer camera kamer
    police policia polizia
    service services dienst diensten servicios
    ecole technical
    group groupe gruppo grupp
    society clinic hub park campus
    ehf hf ry rf vzw asbl ggmbh gug cic ngo npo gie eeig
    anonim sirketi dernegi vakfi
    sihtasutus mittetulundusuhing
    ikke idiotiki etaireia etaireias kefalaiouchiki epitropi panepistimio panepistimiou
    laiki stoicheion
    district district okres powiat gmina wojewodztwo
    ayuntamiento diputacion generalitat junta cabildo
    ceska slovenska polska
    asociata obsteasca
    institucija bendrija uzdaroji akcine
    eric ente az sint culture cultural connect conservatorio conservatoire clusterul irt foiskola srls ltda
    consorzio consorci consorcio culturale kulturni
    ellinikos erythros asocijacija zdruzenie zdruzenia voedsel escola concello aktiebolaget healthcare pays petr ance
    syllogos dikigorikos limitada
    saint san santa sao sankt sanitari sanitaria ospedaliera azienda nemocnica collectivite kolej confindustria
    parc gesmbh gesmbh
""".split())

# A stem inside a compound ("Filmuniversitat", "Elektroinstitut", "Ziekenhuis") makes a word organisational.
_ORG_STEMS = ("univers", "institut", "akadem", "academ", "fundac", "fondaz", "stiftung", "consorz", "ziekenhuis",
              "krankenhaus", "sjukhus", "sairaala", "klinik", "clinic", "zentrum", "cluster", "genossen",
              "gesellschaft", "forschung", "research", "technolog", "engineer", "foisk", "hogeschool", "laborator", "rannsokn")

# Organisations named for a person that the rule would otherwise hide (companies and charities, checked).
_NAMED_AFTER_PEOPLE = frozenset({"john cockerill", "carl zeiss", "karl storz", "robert bosch", "anthony nolan",
                                 "max planck", "alan turing", "marie curie", "georg fischer", "ernst klett"})

# Particles of a surname; they do not count as words of a name.
_PARTICLES = frozenset("van von der den de di da del della dos das du la le ter ten op het t zu zur af av".split())

# Given names, folded (no accents, lower case). Ambiguous with a place or a common word are left out
# (paris, florence, victoria, georgia, jordan, austin, orlando, grace, rose, hope, max, mark, rich).
_GIVEN = frozenset("""
    james john robert michael william david richard joseph thomas charles christopher daniel matthew anthony donald
    steven paul andrew joshua kenneth kevin brian george timothy ronald edward jason jeffrey ryan jacob gary nicholas
    eric jonathan stephen larry justin scott brandon benjamin samuel gregory alexander frank patrick raymond jack
    dennis jerry tyler aaron adam nathan henry douglas zachary peter kyle walter ethan jeremy harold keith christian
    roger noah gerald carl terry sean arthur lawrence jesse dylan bryan joe billy bruce albert gabriel logan alan wayne
    roy ralph randy eugene vincent russell louis bobby philip johnny colin stuart graham neil malcolm duncan angus
    ian gordon hamish fergus callum niall declan eoin cian conor seamus padraig ciaran liam oisin donal brendan
    mary patricia jennifer linda elizabeth barbara susan jessica sarah karen lisa nancy betty margaret sandra ashley
    kimberly emily donna michelle carol amanda dorothy melissa deborah stephanie rebecca sharon laura cynthia
    kathleen amy angela shirley anna brenda pamela emma nicole helen samantha katherine christine debra rachel
    carolyn janet catherine maria heather diane olivia julie joyce ruth virginia lauren kelly christina joan evelyn
    judith andrea hannah megan cheryl jacqueline martha teresa gloria sara janice ann kathryn abigail sophia frances
    jean alice judy isabella julia amber denise danielle marilyn beverly charlotte natalie theresa diana brittany
    doris kayla alexis lori marie fiona moira siobhan niamh aoife sinead orla roisin caoimhe grainne aisling
    hans klaus wolfgang jurgen gunter gunther uwe dieter manfred horst heinz helmut werner bernd rolf rainer jorg
    joerg karl heiko lars jens thorsten torsten sven stefan andreas markus matthias martin ralf holger dirk volker
    herbert gerhard gerd fritz otto kurt ernst erwin rudolf rudiger siegfried hartmut egon elmar sebastian florian
    tobias nils niklas philipp felix lukas leon maximilian julian simon fabian marcel marco mario oliver jonas
    moritz henrik hendrik friedrich heinrich wilhelm ludwig lothar norbert reinhard reinhold rainer ulrich ulf
    konrad kilian bastian benedikt clemens dominik elias emil johannes jakob josef joachim jochen juergen
    maria ursula monika petra sabine renate karin brigitte gisela erika ingrid helga christa gabriele angelika
    birgit susanne claudia martina heike silke katrin kerstin jutta ute andrea sandra stefanie nicole melanie
    sabrina tanja yvonne daniela corinna carina carola annette antje bettina dagmar doris elke gerda gertrud
    hannelore irene ilse inge irmgard johanna kirsten lena lisbeth margit marlene regina rita rosemarie sigrid
    sonja steffi sybille tina vera waltraud
    jean pierre michel philippe alain jacques bernard marcel rene andre claude francois nicolas laurent olivier
    thierry julien guillaume antoine mathieu maxime hugo lucas romain xavier yves gilles pascal didier stephane
    frederic jerome fabrice cedric christophe benoit sylvain gael loic anthony quentin valentin remi remy herve
    henri gerard lucien raymond georges roland serge bruno denis dominique emmanuel etienne eric fabien franck
    gregory ludovic mickael patrice rodolphe thibault tristan vincent yannick
    marie nathalie isabelle sylvie catherine francoise monique christine sophie valerie veronique martine anne
    celine camille sandrine laurence brigitte nadine chantal corinne delphine fabienne genevieve ghislaine helene
    jacqueline josette karine lucie magali manon margaux mireille murielle odile pascale patricia sonia stephanie
    sylviane therese vanessa viviane yvette aurelie aurore beatrice clemence clementine elodie emilie estelle
    jose juan antonio manuel francisco javier miguel angel carlos luis pedro jesus alejandro rafael fernando pablo
    sergio jorge alberto ramon enrique diego ignacio rodrigo santiago alvaro ruben ivan oscar victor hector
    eduardo joaquin cesar gonzalo guillermo salvador agustin andres gabriel gustavo
    carmen ana isabel dolores pilar rosa cristina marta elena lucia paula raquel beatriz filipa ines joana
    mercedes concepcion josefa antonia francisca luisa rosario encarnacion montserrat nuria silvia sonia
    susana teresa yolanda eva irene lorena mireia noelia olga patricia rocio sandra
    joao jose antonio paulo nuno rui tiago bruno ricardo fabio goncalo duarte vasco afonso
    giovanni giuseppe mario luigi francesco angelo vincenzo pietro salvatore carlo franco domenico paolo michele
    giorgio aldo luca marco alessandro roberto stefano giancarlo massimo fabio antonino antonello bartolomeo
    claudio cosimo daniele emilio enrico enzo ettore fabrizio gaetano gianni gianluca gianfranco ignazio lorenzo
    luciano maurizio mauro nicola nunzio onofrio orazio piero raffaele renato riccardo rocco rosario sandro
    santo saverio silvio simone tommaso ugo umberto valerio vito
    giovanna giuseppina angela francesca carmela caterina concetta antonella chiara elisabetta federica giulia
    giuliana lucia luisa margherita paola patrizia raffaella roberta rosaria serena silvia simona stefania
    valentina viviana cinzia daniela donatella elena eleonora gabriella grazia ilaria laura lidia loredana manuela
    marina marisa michela monica nadia rossella sabrina tiziana
    jan johannes pieter hendrik cornelis willem gerrit jacobus petrus adrianus theodorus wilhelmus johan
    dirk kees koen bram sander stijn thijs joost wouter pim sjoerd ruud rob erik gijs maarten niels ruben
    johanna elisabeth cornelia geertruida wilhelmina petronella adriana henrica jacoba catharina hendrika
    marijke annelies anneke els femke ingrid karin lieke lotte marloes marieke nienke renske sanne yvonne
    erik anders karl johan olof gunnar bengt mats magnus lennart stig nils bjorn sven ulf leif
    kjell knut arne rune bjarne torbjorn thor odd trygve havard
    anna eva karin ingrid kristina maria marie margareta birgitta lena annika gunilla cecilia elisabet
    risto kalervo juha mikko timo matti antti jari pekka kari markku petri heikki jukka tapio veikko
    seppo reijo ilkka hannu pentti sakari eero
    aino helmi kaisa leena liisa marja outi paivi riitta sirkka tuula ulla
    gitte lene mette hanne helle inge jette karen kirsten lone pia susanne tina anja
    jens kasper klaus lars mads morten preben rasmus soren thomas torben
    jiri josef petr pavel tomas jaroslav miroslav libor zdenek vaclav frantisek milan jakub ondrej radek
    vladimir lubomir ladislav stanislav bohumil roman marek michal lukas martin patrik
    jana eva hana lenka lucie marie petra veronika zuzana martina katerina ivana barbora
    piotr andrzej krzysztof tomasz pawel marcin jacek grzegorz rafal marek lukasz waldemar kazimierz zbigniew
    mariusz dariusz artur arkadiusz bartlomiej dawid wojciech jerzy henryk ryszard slawomir tadeusz janusz
    miroslaw leszek edward bogdan damian kamil maciej przemyslaw jaroslaw radoslaw mateusz karol szymon filip
    kacper patryk norbert zdzislaw wladyslaw bernard cezary czeslaw ireneusz kornel lech marian mieczyslaw stefan
    krystyna iwona jadwiga malgorzata katarzyna agnieszka ewa joanna magdalena monika elzbieta zofia danuta halina
    renata beata aleksandra dorota natalia hanna ilona jolanta wanda lucyna alicja marzena urszula grazyna bozena
    sylwia paulina justyna karolina weronika wioletta ewelina kinga
    istvan laszlo jozsef janos zoltan sandor gabor attila balazs bela csaba ferenc geza gyorgy imre karoly lajos
    miklos peter tamas tibor viktor zsolt
    maria erzsebet katalin ilona margit zsuzsanna judit eva agnes aniko eniko hajnalka
    ion gheorghe vasile constantin nicolae mihai ioan alexandru marian florin ionut costel dumitru cristian
    adrian bogdan catalin cosmin dan dorin liviu marius radu sorin stelian valentin viorel
    elena maria ioana ana mihaela cristina daniela georgeta gabriela mariana monica nicoleta rodica simona
    ivan georgi dimitar petar nikolay stoyan hristo todor krasimir plamen rosen kiril boris vasil
    stoyanka ivanka petya tsvetanka
    georgios ioannis konstantinos dimitrios nikolaos christos panagiotis athanasios vasileios evangelos
    theodoros spyridon michail apostolos stavros
    mehmet mustafa ahmet ali hasan huseyin ibrahim ismail osman murat yusuf emre burak serkan kemal
    ayse fatma emine hatice zeynep elif
    janis andris ivars martins aivars juris edgars arturs ilmars valdis
    jonas antanas petras vytautas algirdas darius mindaugas rimas saulius tomas gintaras
    tonu jaan andres toomas peeter mati kalev raivo margus
    mihkel ants priit
    viktor sergei sergey andrey dmitry dmitri alexei aleksei vladimir oleg yuri yury igor oleksandr oleksiy
    mykola taras bohdan andriy volodymyr serhiy
    olga natalia svetlana tatiana irina oksana iryna
    ahmed mohamed mohammed omar khaled hassan hussein abdul abdullah youssef karim tarek samir
    david daniel jonathan joel yossi
    bob tom tim jim sam ben ron ted bill mike dave steve andy tony nick jeff greg phil rick pete chris matt josh
    alex lee kim jay ray
    eduard liana philibert adalbert albrecht alfred alois amadeus anselm armin arnold arno aurel axel balthasar
    benno bernhard berthold bertram burkhard christoph cornelius dietrich dietmar eberhard eckhard edgar edmund
    egbert ekkehard emanuel engelbert eugen ewald ferdinand franz friedhelm georg gerold gottfried gregor guido
    gustav hagen harald harry hartwig hasso heribert hermann hubert ingo isidor justus kaspar klemens lambert
    leonhard leopold lorenz lutz manuel marius mathias maurice meinhard melchior michel nikolaus norman oskar
    othmar peer rainald raimund robin roland roman rupert sascha siegmund sigmund sigurd stephan tilman udo urs
    veit volkmar wendelin wenzel wieland willi winfried wolfram xaver zacharias
    adelheid agathe agnes alexandra alina amalie anette antonia astrid berit bianca birte brunhild carmen
    christel christiane clara claudine constanze cornelia dorothea edith elfriede ella ellen elsa erna
    esther eugenie felicitas frauke friederike gabi gerlinde gesine gudrun hedwig heidi heidrun helene henriette
    hertha hilde ida isolde jasmin jule karolin katharina klara kristin laila lea leonie liane lilli lore lotte
    louise luise lydia magda mareike margarete marianne marlies mathilde mia nadja nele nina ricarda roswitha
    selma sieglinde tamara thea theresia ulrike verena veronika viola wiebke wilma zita
    addie arjan bart bas bert bernardus boudewijn cees daan dick dolf eelco evert frans gerard gert gijsbert
    harm jaap jacco jelle jeroen joep jorrit klaas laurens luuk martijn mathijs menno michiel nico olaf pepijn rik
    robbert roel roelof rutger siebe sjors teun tijs ton wim yorick
    anouk carla carolien dorien eline esmee fleur gea hanneke jolanda karlijn liesbeth lies mirjam noor puck
    saskia sofie suzanne tessa wendy
    jordi joan pau pere josep lluis narcis jaume ferran marc oriol arnau laia montse merce meritxell iker aitor
    unai jon mikel asier imanol koldo xabier maite itziar amaia nerea leire maialen arantza xoan xose brais
    matteo gabriele giacomo damiano emanuele leonardo davide edoardo pasquale ciro gennaro attilio livio nello
    tullio elio ennio gino lino rino remo vittorio assunta elvira ornella nicoletta annamaria mariangela
    eleni katerina sofia vasiliki ioanna dimitra anastasia evangelia panagiota despina konstantina antonios
    emmanouil grigorios leonidas pavlos petros stylianos alexandros charalampos eleftherios
    levent can cem emir kerem mert onur tolga volkan yasin ozlem sevgi
    liana ligita dace inese ilze zane inga sandra egils gunars uldis raimonds eriks roberts normunds
    rasa jurate daiva vilma audrone ruta ramune
    kaido hannes tiit urmas jaak meelis
    melina jill vesela jeppe hubrecht
    karlheinz karlheinrich hansjoerg hansjuergen hansjoachim klausdieter wolfdieter heinzwerner rolfdieter
    virginio ambrogio ottavio tiziano flavio fulvio gianpaolo giampiero pierluigi piergiorgio pierpaolo ivano
    ivo dino enea osvaldo adriano graziano severino vitale
    hagit yael noa dana tamar shira moshe avi eli ofer amir gil yossi
    catrin rhys gareth dafydd bethan megan ffion owain iwan
    sebastien carsten catalina fatmir leylah
    casper peder flemming finn jesper henning bent ejnar ove svend jorgen kristian lasse christoffer mikkel mogens
    poul erling tage mientje jennigje grietje geertje aaltje hendrikje dirkje maaike
    arun rajesh sunil anil suresh ramesh vikram rahul amit sanjay priya anita sunita kavita deepak ashok manoj
    vijay ravi pradeep srinivas lakshmi meera amila
""".split())
# Given names that are also an acronym or a common word in some language ("CAN", "BAS", "TON", "PAU"): a
# one-in-a-thousand person is not worth hiding the organisations called that.
_GIVEN -= frozenset("can ton ray ida gea bas rik lies kim leo jay pau ana".split())


def individual_reason(name: str | None, country: str | None = None) -> str | None:
    """Why this organisation is treated as a natural person, or None when it is not."""
    raw = (name or "").strip()
    if not raw:
        return None
    words = _words(raw)
    if not words:
        return None
    if " ".join(words) in _NAMED_AFTER_PEOPLE or any(" ".join(words).startswith(n + " ") for n in _NAMED_AFTER_PEOPLE):
        return None
    wordset = set(words)
    parts = {p for w in words for p in w.split("-")}
    has_given = bool(parts & _GIVEN)
    # a sole-proprietor form beside a given name: the business is a person
    sole = wordset & _SOLE_TRADER or wordset & _SOLE_TRADER_BY_COUNTRY.get(country or "", frozenset())
    if sole and has_given:
        return "sole_trader_form"
    # the owner's name in a trailing parenthesis: "ARENDT BUSINESS CONSULTING (HANS-HENNING ARENDT)". The
    # first word of the parenthesis is a given name; an acronym such as "(EU-OPENSCREEN ERIC)" is not.
    m = re.search(r"\(([^()]{3,60})\)\s*$", raw)
    if m:
        inner = _words(m.group(1))
        if (2 <= len(inner) <= 3 and set(inner[0].split("-")) & _GIVEN
                and not set(inner) & (_CORPORATE | _ORG_WORDS)):
            return "owner_in_parenthesis"
    if wordset & _CORPORATE or wordset & _ORG_WORDS or any(stem in w for w in words for stem in _ORG_STEMS):
        return None
    tokens = [t for t in re.split(r"[\s,;]+", raw.replace(".", " ")) if t]
    if not 2 <= len(tokens) <= 5:
        return None
    if not all(re.fullmatch(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*", t) for t in tokens):
        return None
    core = [w for w in words if w not in _PARTICLES]
    if len(core) < 2 or len(core) > 4:
        return None
    if has_given:
        return "person_name"
    return None


def mark_individuals(conn: psycopg.Connection, *, write: bool = True) -> dict[str, int]:
    """Set `organisation.individual_reason` for every organisation that took part in a project, from its name.

    Idempotent and symmetric: a verdict that no longer holds (the list was corrected) is cleared. Only
    organisations with a participation are looked at; the others are not in the directory anyway. Returns
    {checked, individuals, changed, <reason>: n}."""
    rows = conn.execute(
        """SELECT o.id, COALESCE(o.display_name, o.canonical_name) AS name, o.country, o.individual_reason
             FROM organisation o
            WHERE EXISTS (SELECT 1 FROM participation pa WHERE pa.organisation_id = o.id)""").fetchall()
    out: dict[str, int] = {"checked": len(rows), "individuals": 0, "changed": 0}
    set_to: dict[str, list[int]] = {}
    clear: list[int] = []
    for r in rows:
        why = individual_reason(r["name"], r["country"])
        if why:
            out["individuals"] += 1
            out[why] = out.get(why, 0) + 1
        if why != r["individual_reason"]:
            out["changed"] += 1
            if why:
                set_to.setdefault(why, []).append(r["id"])
            else:
                clear.append(r["id"])
    if write:
        for why, ids in set_to.items():
            conn.execute("UPDATE organisation SET individual_reason = %s WHERE id = ANY(%s)", (why, ids))
        if clear:
            conn.execute("UPDATE organisation SET individual_reason = NULL WHERE id = ANY(%s)", (clear,))
    return out
