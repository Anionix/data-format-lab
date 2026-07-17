# GeoNames cities500

This directory contains a four-row fixture and a full normalized benchmark snapshot for the daily GeoNames `cities500.zip` export. The full source has 234,934 rows and 19 tab-separated fields and is mutable. The benchmark selects seven fields, while the normalizer validates all 19 fields, converts blank fields to NULL, and records the archive/member hashes. The full CSV is distributed as a checksum-pinned Release asset.

Source: [GeoNames export](https://download.geonames.org/export/dump/cities500.zip), [export terms](https://www.geonames.org/export/), CC BY 4.0 with GeoNames attribution and an as-is quality caveat.
