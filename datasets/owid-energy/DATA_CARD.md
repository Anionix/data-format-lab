# OWID Energy

This directory contains a four-row fixture and a full normalized benchmark snapshot for the OWID energy CSV. The observed official download has 23,377 rows and 130 columns. The benchmark selects `country`, `year`, `population`, `renewables_share_energy`, and `energy_per_capita`; the checksum-pinned Release asset is derived from the observed public download. The GitHub-pinned rounded CSV is a different source variant and must not be silently mixed with the public download.

Source: [OWID energy CSV](https://owid-public.owid.io/data/energy/owid-energy-data.csv) and [codebook](https://github.com/owid/energy-data/blob/master/owid-energy-codebook.csv). OWID-produced material is CC BY; underlying source licenses remain separate.
