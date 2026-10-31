/**
 * What the "open to Ukraine" flag of a call says, in words (V2-C U3, V2-B2, V2-B9). The readiness card of the EDF, the regulatory tracker and this
 * sentence say the same thing about Ukraine and the EDF: an associated country since 16 October 2026 (WP-167), in the Commission's words.
 * lib/ukraine.check.ts and lib/wp167.check.ts run it.
 */

/** WP-167: the DG DEFIS news of 16 October 2026 (backend/dgate/ukraine.py EDF_IN_FORCE_URL, EDF_IN_FORCE), word for word. */
export const EDF_IN_FORCE_URL = 'https://defence-industry-space.ec.europa.eu/ukraines-association-european-defence-fund-and-european-defence-industry-porgramme-funding-entered-2026-10-16_en';
export const EDF_IN_FORCE = 'The Ukrainian association with the European Defence Fund (EDF) and financing under the European Defence Industry Programme (EDIP) agreements have come into force.';

/** WP-167: an EDF call that closed before Ukraine's association entered into force ('edf_association_unconfirmed' until the flags are re-run). */
export function beforeAssociation(reason: string | null | undefined): boolean {
  return reason === 'edf_closed_before_association' || reason === 'edf_association_unconfirmed';
}

/** What the Ukraine flag says, in a sentence. Null: nothing to show. */
export function ukraineSentence(flag: boolean | null | undefined, reason: string | undefined): string | null {
  if (flag === true && reason === 'edf_association') {
    return 'Ukrainian entities may take part in this call: Ukraine is an associated country of the European Defence Fund since 16 October 2026, '
      + 'when the European Commission said its association agreement had come into force.';
  }
  if (flag === true) return 'Ukrainian entities may take part in this call.';
  if (flag === false) {
    if (reason === 'programme_rule') {
      return 'Not for the recipient types this call names. Recipients of EDIP funding must be established in the Union or in an EEA EFTA associated country, and Ukraine is not an associated country of the Programme. '
        + 'Ukraine can still take part in other ways, for example by designating a procurement agent or as a member of a SEAP, and Ukrainian entities are served by the Ukraine Support Instrument.';
    }
    if (reason === 'call_document_closed_list') {
      return 'The call document lists the eligible countries one by one (the Member States and the EEA countries Norway, Iceland and Liechtenstein). Ukraine is not on the list.';
    }
    return 'The source says Ukrainian entities may not take part in this call.';
  }
  if (beforeAssociation(reason)) {
    return 'This call closed before 16 October 2026, when Ukraine’s association with the European Defence Fund entered into force. '
      + 'Its call document said that participation of entities established in Ukraine was pending the signature of the association agreement, so we do not mark this call open or closed.';
  }
  // WP-145: an EDIP call whose own document says it (backend/dgate/ukraine.py no_funding_sentence): its sentence is quoted under this one
  if (reason === 'call_document_no_funding') return 'Ukrainian entities cannot receive funding under this call: the call document says so.';
  if (reason === 'programme_rule') {
    // WP-132 (round-7 audit, 116 and 117): "Not decided" stood beside a check that blocks a Ukrainian company under the same Regulation.
    // The flag stays unknown (no sentence of the call says it, V3-A), but the answer for an applicant is the Regulation's, said once.
    return 'Entities established in Ukraine cannot receive EDIP funding under this call: recipients must be established in the Union or in an EEA EFTA associated country, '
      + 'and Ukraine is not an associated country of the Programme (Regulation (EU) 2025/2643, Articles 9(1) and 2). The eligibility check on this page applies that rule. '
      + 'Where the call document names Ukraine, it is in another role (for example as a member of a SEAP or as a state that designates a procurement agent); '
      + 'Ukrainian entities are served by the Ukraine Support Instrument.';
  }
  return null;
}
