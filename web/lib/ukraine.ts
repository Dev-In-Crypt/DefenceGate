/**
 * What the "open to Ukraine" flag of a call says, in words (V2-C U3, V2-B2, V2-B9). The readiness card of the EDF, the regulatory tracker and this
 * sentence say the same thing about Ukraine and the EDF: conditional on the association agreement, not confirmed. lib/ukraine.check.ts runs it.
 */

/** What the Ukraine flag says, in a sentence. Null: nothing to show. */
export function ukraineSentence(flag: boolean | null | undefined, reason: string | undefined): string | null {
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
  if (reason === 'edf_association_unconfirmed') {
    return 'Conditional on the association agreement, not confirmed. Ukraine may take part in the European Defence Fund as an associated country under the EU-Ukraine association agreement, '
      + 'but the EDF call documents say that participation of entities established in Ukraine is pending the signature of that agreement, and we have found no official text that says it is in force. We do not mark this call open or closed.';
  }
  if (reason === 'programme_rule') {
    return 'Not decided. Recipients of EDIP funding must be established in the Union or in an EEA EFTA associated country, which Ukraine is not. '
      + 'No sentence we hold says whether entities established in Ukraine may apply to this call; where its document names Ukraine at all, it is in another role (for example as a member of a SEAP or as a state that designates a procurement agent). We do not mark this call open or closed.';
  }
  return null;
}
