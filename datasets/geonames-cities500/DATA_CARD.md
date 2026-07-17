# GeoNames cities500

This directory contains a four-row fixture for the daily GeoNames `cities500.zip` export. The full source has 19 tab-separated fields and is mutable. A full capture must preserve the ZIP/member hashes, validate exactly 19 fields, convert blank fields to NULL, and sort only in the normalized table contract.

Source: [GeoNames export](https://download.geonames.org/export/dump/cities500.zip), [export terms](https://www.geonames.org/export/), CC BY 4.0 with GeoNames attribution and an as-is quality caveat.
