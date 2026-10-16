# Why this is the appropriate successor

Research date: October 13, 2026. The sources below are primary materials from the issuing organizations. The product direction is our inference from the original repository and these workflows; it is not evidence that a customer has validated demand.

## The work to serve

The defensible first audience is an export-compliance analyst at a manufacturer, exporter, or distributor, with a reviewer who can assess unresolved questions. BIS describes an inquiry-and-reevaluation process when circumstances raise concerns. That work needs the records behind a transaction, explicit unresolved questions, and a retained assessment. [BIS Know Your Customer guidance](https://www.bis.gov/node/1533).

Counterparty screening must separate name similarity from identity resolution and the legal effect of a listing. OFAC describes checking the relevant list and other identifying information; its search score describes similarity. Accordingly, omphalOS produces candidates with supporting and conflicting fields, preserves list/source category, and requires human assessment. [OFAC FAQ 5](https://ofac.treasury.gov/faqs/5), [OFAC FAQ 247](https://ofac.treasury.gov/faqs/247).

An investigation also needs shipping and financial context. BIS forwarder guidance discusses classification, authorizations, and inconsistencies in shipping documentation. The FinCEN–BIS notice describes diversion indicators in customer, payment, and trade records. Those indicators justify questions; they do not prove wrongdoing. [BIS forwarder guidance](https://www.bis.gov/learn-support/export-compliance-programs/freight-forwarder-guidance), [FinCEN–BIS notice](https://www.fincen.gov/system/files/shared/FinCEN_Joint_Notice_US_Export_Controls_FINAL508.pdf).

## Data that can actually support it

**Analyst-supplied transaction files** are essential. A public aggregate trade dataset does not contain the exporter/importer identities, payment records, and documentary context needed for individual cases. UN Comtrade is useful for aggregate context, with distinct access and reuse terms; it is not a substitute for these records. [UN Comtrade](https://comtradeplus.un.org/).

**ITA CSL bulk JSON** can be downloaded without an API key and kept locally. The keyed search API is a different service. Our live probe found 26,128 records and retained publisher metadata. It also found expired Denied Persons List records, including an end date in 2000. Preserve start/end dates and underlying source categories rather than declaring every row a current prohibition. [ITA CSL downloads](https://www.trade.gov/consolidated-screening-list), [official JSON endpoint](https://data.trade.gov/downloadable_consolidated_screening_list/v1/consolidated.json).

**OFAC SDN and non-SDN XML** are separately supported. Non-SDN listings must not be labeled SDN blocking determinations. Raw snapshots and retrieval metadata accompany every source. [OFAC Sanctions List Service](https://ofac.treasury.gov/sanctions-list-service).

GLEIF identity data, the UK Sanctions List, and UN reference data are credible later additions. They were researched; they are not advertised as shipped adapters. External identity searches would need a deliberate privacy choice rather than silently sending private names to a service.

## Rules must remain time- and jurisdiction-aware

An HS/HTS code is not an ECCN. Classification requires technical facts; omphalOS preserves the two fields separately. [BIS classification guidance](https://www.bis.gov/licensing/classify-your-item).

OFAC ownership aggregation and indirect ownership cannot be replaced by generic multiplication of stakes. Nor can OFAC logic be transplanted to every BIS list. As of the research date, BIS's Affiliates Rule was stayed through November 9, 2026; scheduled changes require fresh verification. The release consequently preserves ownership evidence without claiming an automated legal-rule engine. [OFAC FAQ 401](https://ofac.treasury.gov/faqs/401), [BIS suspension rule](https://www.federalregister.gov/documents/2025/11/12/2025-19846/one-year-suspension-of-expansion-of-end-user-controls-for-affiliates-of-certain-listed-entities).

## Evidence design

Separate source material, transformations, observations, and people responsible for interpretation. This uses the conceptual distinctions in W3C PROV without asserting full PROV conformance. The exported application ZIP inventories every file; it is not mislabeled BagIt or RO-Crate. A standards-based exchange adapter can be added when a receiving workflow requires it. [W3C PROV overview](https://www.w3.org/TR/prov-overview/), [BagIt specification](https://www.rfc-editor.org/rfc/rfc8493.html), [RO-Crate 1.3](https://www.researchobject.org/ro-crate/specification/1.3/index.html).

Hashes establish a comparison against known bytes. They do not establish truth, independent custody, or the identity of a reviewer. These separate claims remain separate in the application and its reports. A verifiable artifact is useful evidence for a later human assessment; it is not a guarantee of legal admissibility.
