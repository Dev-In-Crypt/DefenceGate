/**
 * WP-97 (persona round of 23 October 2026, section B): the national supply route of a supplier's own country, beside the NATO and EU steps
 * of its roadmap and report. Only what a primary source already in the repository states: the German rules of the requirements seed
 * (BAFA and the export list, AWV § 8 and § 11 and AWG § 13; the BMWE security FAQ), the federal notice service we read
 * (docs/sources/de_national.md) and the buyers of our own data (the notices themselves). What no such source settles is said plainly,
 * "Not covered yet for <country>", with the body to ask, which a primary source in the repository names; no issuer, cost or time is
 * invented. Spain has its own route in the rules (the Ministry of Defence route), so it has no lines here. Pure data and one function;
 * lib/wp97.check.ts holds it.
 */
import { NSPA_NCAGE_URL, ncageText } from './readiness';
import { countryInText } from './taxonomy';

export interface RouteLine {
  key: string;
  title: string;
  text: string;
  /** A page of the source (outside) or of this site (inside, starting with "/"). */
  link: { label: string; url: string } | null;
  /** True for "Not covered yet": what to check, and with whom. */
  open: boolean;
}

const notCovered = (country: string, what: string, ask: string) => `Not covered yet for ${countryInText(country)}: ${what}. Check with ${ask}.`;

/** The NCAGE line, in the words the roadmap and the requirement page use (`issuerFor`): NSPA's request page is where it starts. */
export function ncageLine(country: string): RouteLine {
  return {
    key: 'ncage', title: 'NCAGE code', open: true, text: ncageText(country),
    link: { label: 'NSPA: request an NCAGE code', url: NSPA_NCAGE_URL },
  };
}

export const COUNTRY_ROUTES: Record<string, RouteLine[]> = {
  DE: [
    {
      key: 'de-buyer', title: 'Selling to the Bundeswehr', open: false,
      text: 'The Federal Office of Bundeswehr Equipment, Information Technology and In-Service Support (BAAINBw) publishes its tenders on TED and on the federal notice service (Bekanntmachungsservice, oeffentlichevergabe.de), which we read; its open tenders and past awards are on its buyer page here.',
      link: { label: 'BAAINBw and the other German defence buyers', url: '/buyers?country=DE&q=BAAINBw' },
    },
    {
      key: 'de-notices', title: 'Where German notices are published', open: false,
      text: 'The federal notice service of the Beschaffungsamt des BMI publishes the notices of German public buyers, below the EU thresholds too; each notice names the platform where its documents are.',
      link: { label: 'oeffentlichevergabe.de', url: 'https://oeffentlichevergabe.de/' },
    },
    {
      key: 'de-export', title: 'Export control (BAFA)', open: false,
      text: 'Exporting goods in Part I Section A (arms) or Section B (national dual-use list) of the German export list, and transferring Section A goods to another EU country, needs a licence from BAFA (AWV § 8 and § 11, AWG § 13). Your results apply this rule to your answers.',
      link: { label: 'AWV § 8 (gesetze-im-internet.de)', url: 'https://www.gesetze-im-internet.de/awv_2013/__8.html' },
    },
    {
      key: 'de-classified', title: 'Classified contracts', open: false,
      text: 'Admission to the Geheimschutzbetreuung of the BMWE is applied for by the contracting party that hands over the classified material, not by the company itself, and is free of charge (BMWE security FAQ). Your results apply these rules once you say you need access to classified information.',
      link: { label: 'BMWE: questions on industrial security', url: 'https://www.bmwe-sicherheitsforum.de/ghb/allgemeines/222,0,0,1,0.html' },
    },
    { ...ncageLine('DE') },
    {
      key: 'de-quality', title: 'AQAP quality assurance', open: true,
      text: notCovered('DE', 'who requires and who audits AQAP quality assurance', 'the buyer named in the tender documents (for the Bundeswehr, BAAINBw)'),
      link: null,
    },
  ],
  PL: [
    {
      key: 'pl-buyer', title: 'Selling to the Polish armed forces', open: false,
      text: 'The Armament Agency (Agencja Uzbrojenia) and the Regional Logistics Bases (Regionalne Bazy Logistyczne) publish their tenders on TED and on the national portal e-Zamówienia, which we read; their open tenders and past awards are on their buyer pages here.',
      link: { label: 'Agencja Uzbrojenia and the other Polish defence buyers', url: '/buyers?country=PL&q=Agencja%20Uzbrojenia' },
    },
    {
      key: 'pl-notices', title: 'Where Polish notices are published', open: false,
      text: 'The national portal e-Zamówienia publishes the notices of Polish public buyers; we read it with TED.',
      link: { label: 'e-Zamówienia', url: 'https://ezamowienia.gov.pl/' },
    },
    {
      key: 'pl-licence', title: 'Licences for weapons, ammunition and explosives', open: true,
      text: notCovered('PL', 'the licences to make or trade in weapons, ammunition and explosives, and the industrial security certificate for classified contracts',
        'the buyer, for example the Armament Agency (Agencja Uzbrojenia), whose tender documents state the licences and certificates a bidder must hold'),
      link: null,
    },
    {
      key: 'pl-export', title: 'Export control', open: true,
      text: notCovered('PL', 'which authority licenses exports of military items', 'the buyer or the export rule’s source on your results; the EU dual-use rule there applies to your answers'),
      link: null,
    },
    { ...ncageLine('PL') },
  ],
  // WP-105 (p06, p07): the export authority for military goods, from the official pages read on 24 October 2026 (the issuers of REQ-EXPORT in
  // the requirements seed); the rest of the route is not covered
  NL: [
    notCoveredRoute('NL'),
    {
      key: 'nl-export', title: 'Export control of military goods (CDIU)', open: false,
      text: 'The forms for exporting military goods are at the Central Import and Export Service (CDIU) of Dutch Customs, which reviews the application on behalf of the Ministry of Foreign Affairs against the Dutch arms export policy (Rijksoverheid). The authority for dual-use items is not covered yet: check with the CDIU.',
      link: { label: 'Rijksoverheid: export licence for military goods', url: 'https://www.rijksoverheid.nl/themas/economie/exportcontrole-strategische-goederen/vraag-en-antwoord/exportcontrole-strategische-goederen/wanneer-heb-ik-een-vergunning-nodig-voor-de-export-van-militaire-goederen' },
    },
    { ...ncageLine('NL') },
  ],
  IT: [
    notCoveredRoute('IT'),
    {
      key: 'it-export', title: 'Export control of armament materials (UAMA)', open: false,
      text: 'The Unit for the authorisations of armament materials (UAMA) of the Ministry of Foreign Affairs is the national authority for the authorisations to trade in armament materials (Law 185/1990, article 7-bis). The authority for dual-use items is not covered yet: check with UAMA.',
      link: { label: 'Law 185/1990, article 7-bis (Normattiva)', url: 'https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:1990-07-09;185~art7bis' },
    },
    { ...ncageLine('IT') },
  ],
};

/** The plain line of a country whose national supplier route our sources do not settle. */
function notCoveredRoute(country: string): RouteLine {
  return {
    key: 'route', title: `Supplying the armed forces of ${countryInText(country)}`, open: true, link: null,
    text: notCovered(country, 'a national supplier route (registrations, licences and security clearances of your country)',
      'the buyer named in each tender, whose documents state what a bidder must hold; the NATO and EU steps of your roadmap apply as they are'),
  };
}

/**
 * The national route lines for a company of this country: Germany's and Poland's above; none for Spain (its route is in the rules); for any
 * other country one plain line that it is not covered yet, and the NCAGE line.
 */
export function countryRoute(country: string): RouteLine[] {
  if (!country || country === 'ES' || country === 'XX') return [];
  if (COUNTRY_ROUTES[country]) return COUNTRY_ROUTES[country];
  return [
    notCoveredRoute(country),
    // WP-105: no other country's export authority is named to this one (a Dutch company read "Spain: …; Germany: BAFA")
    {
      key: 'export', title: 'Export control', open: true, link: null,
      text: notCovered(country, 'which authority licenses exports of military and dual-use items',
        'the export-control authority of your country; the EU dual-use rule on your results applies to your answers'),
    },
    ncageLine(country),
  ];
}
