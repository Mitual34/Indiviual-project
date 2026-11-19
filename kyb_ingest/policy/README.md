# Jurisdiction policy files
`jurisdiction_flag` is NOT a data source: it needs a dated policy you define and cite. Create
`high_risk_jurisdictions.csv` with header `country,list_name,effective_from,effective_to` (ISO dates, `effective_to`
may be empty). Typical inputs: UK high-risk third countries list (Money Laundering Regulations 2017, Sch. 3ZA) and
FATF "high-risk" / "increased monitoring" lists. Fill it from the official publications; this repo ships only the header.
If the file is missing or a country is unknown, the pipeline returns None (unknown), never 0.
