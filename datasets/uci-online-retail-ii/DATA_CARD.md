# Online Retail II

This directory contains a four-row fixture and a full normalized benchmark snapshot for the UCI Online Retail II contract. The UCI dataset 502 archive has two sheets with 1,067,371 rows and eight native columns; the benchmark preserves all eight columns and concatenates both sheets in source order. The full CSV is distributed as a checksum-pinned Release asset; the fixture is only for CI smoke tests.

Source: [UCI archive](https://archive.ics.uci.edu/static/public/502/online%2Bretail%2Bii.zip), DOI `10.24432/C5CG6D`, CC BY 4.0. The manifest records observed archive and XLSX member hashes, the concatenation rule, and missing-value policy.
